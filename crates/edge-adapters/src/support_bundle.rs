use std::fs::{self, File, OpenOptions};
use std::io::Read;
use std::path::{Path, PathBuf};
use std::sync::atomic::{AtomicU64, Ordering};
use std::time::SystemTime;

use edge_domain::{
    AppError, DataDirectoryLockState, ErrorCode, SupportBundleArchiveReceipt,
    SupportBundleArtifact, SupportBundleOmission, SupportBundleOmissionReason,
};
use edge_ports::{
    DataDirectoryLockGuard, SupportBundleCollector, SupportBundleReport, SupportBundleRequest,
};
use sha2::{Digest, Sha256};

/// Filesystem collector for the fixed, allowlisted support-artifact layout.
/// It does not accept caller-supplied source paths or archive member names.
#[derive(Debug)]
pub struct FileSupportBundleCollector {
    root: PathBuf,
    output: PathBuf,
    offline_lock: Option<Box<dyn DataDirectoryLockGuard>>,
}

impl FileSupportBundleCollector {
    /// Atomically publishes only known support sources under the fixed private layout.
    /// The caller supplies already-redacted summaries; arbitrary paths are not accepted.
    pub fn publish_sources(
        &self,
        sources: &[(SupportBundleArtifact, Vec<u8>)],
    ) -> Result<(), AppError> {
        ensure_private_support_directory(&self.root)?;
        let mut seen = Vec::new();
        let mut total_bytes = 0_u64;
        for (artifact, contents) in sources {
            if seen.contains(artifact) || contents.len() > 512 * 1024 {
                return Err(support_error("support source set is invalid"));
            }
            seen.push(*artifact);
            total_bytes = total_bytes.saturating_add(contents.len() as u64);
            if total_bytes > edge_domain::SupportBundleBounds::SAFE_DEFAULT.max_total_bytes {
                return Err(support_error("support source set exceeds its bound"));
            }
            let (relative, _) = Self::source_for(*artifact);
            let target = self.root.join(relative);
            if relative.starts_with("config/") {
                ensure_private_support_child(&self.root, "config")?;
            } else if relative.starts_with("logs/") {
                ensure_private_support_child(&self.root, "logs")?;
            }
            match fs::symlink_metadata(&target) {
                Ok(metadata) if metadata.is_file() && !metadata.file_type().is_symlink() => {}
                Ok(_) => return Err(support_error("support source path is unsafe")),
                Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
                Err(_) => return Err(support_error("support source path is unavailable")),
            }
        }

        for (artifact, contents) in sources {
            let (relative, _) = Self::source_for(*artifact);
            publish_private_support_source(&self.root.join(relative), contents)?;
        }
        Ok(())
    }

    pub fn new_online(root: impl AsRef<Path>, output: impl AsRef<Path>) -> Self {
        Self {
            root: root.as_ref().to_path_buf(),
            output: output.as_ref().to_path_buf(),
            offline_lock: None,
        }
    }

    pub fn new_offline(
        root: impl AsRef<Path>,
        output: impl AsRef<Path>,
        lock: Box<dyn DataDirectoryLockGuard>,
    ) -> Result<Self, AppError> {
        if lock.state() != DataDirectoryLockState::HeldExclusive {
            return Err(AppError::new(
                ErrorCode::DataDirectoryLockStateInvalid,
                "offline support bundle requires an exclusive data lock",
            ));
        }
        Ok(Self {
            root: root.as_ref().to_path_buf(),
            output: output.as_ref().to_path_buf(),
            offline_lock: Some(lock),
        })
    }

    fn source_for(artifact: SupportBundleArtifact) -> (&'static str, &'static str) {
        match artifact {
            SupportBundleArtifact::VersionManifest => ("version.manifest", "version.manifest"),
            SupportBundleArtifact::MaskedConfig => ("config/masked.toml", "config/masked.toml"),
            SupportBundleArtifact::BoundedProductLog => ("logs/product.log", "logs/product.log"),
            SupportBundleArtifact::HealthSummary => ("health.json", "health.json"),
            SupportBundleArtifact::ResourceSummary => ("resource.json", "resource.json"),
            SupportBundleArtifact::AuditSummary => ("audit-summary.json", "audit-summary.json"),
        }
    }
}

fn support_error(message: &'static str) -> AppError {
    AppError::new(ErrorCode::SupportBundleReportInvalid, message)
}

fn ensure_private_support_directory(path: &Path) -> Result<(), AppError> {
    let metadata = fs::symlink_metadata(path)
        .map_err(|_| support_error("support directory is unavailable"))?;
    if !metadata.is_dir() || metadata.file_type().is_symlink() {
        return Err(support_error("support directory is unsafe"));
    }
    set_private_support_directory_permissions(path)
        .map_err(|_| support_error("support directory permissions failed"))
}

fn ensure_private_support_child(root: &Path, child: &'static str) -> Result<(), AppError> {
    let path = root.join(child);
    match fs::symlink_metadata(&path) {
        Ok(metadata) if metadata.is_dir() && !metadata.file_type().is_symlink() => {}
        Ok(_) => return Err(support_error("support source directory is unsafe")),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            fs::create_dir(&path)
                .map_err(|_| support_error("support source directory cannot be created"))?;
        }
        Err(_) => return Err(support_error("support source directory is unavailable")),
    }
    set_private_support_directory_permissions(&path)
        .map_err(|_| support_error("support source directory permissions failed"))
}

fn publish_private_support_source(path: &Path, contents: &[u8]) -> Result<(), AppError> {
    static NEXT_TEMP_ID: AtomicU64 = AtomicU64::new(1);
    let parent = path
        .parent()
        .ok_or_else(|| support_error("support source parent is unavailable"))?;
    let file_name = path
        .file_name()
        .and_then(|name| name.to_str())
        .ok_or_else(|| support_error("support source name is invalid"))?;
    let temporary = parent.join(format!(
        ".{file_name}.{}.{}.tmp",
        std::process::id(),
        NEXT_TEMP_ID.fetch_add(1, Ordering::Relaxed)
    ));
    let mut options = OpenOptions::new();
    options.write(true).create_new(true);
    #[cfg(unix)]
    {
        use std::os::unix::fs::OpenOptionsExt;
        options.mode(0o600).custom_flags(libc::O_NOFOLLOW);
    }
    let result = (|| {
        let mut file = options
            .open(&temporary)
            .map_err(|_| support_error("support source cannot be staged"))?;
        std::io::Write::write_all(&mut file, contents)
            .map_err(|_| support_error("support source cannot be written"))?;
        file.sync_all()
            .map_err(|_| support_error("support source cannot be synced"))?;
        crate::set_private_file_permissions(&temporary)
            .map_err(|_| support_error("support source permissions failed"))?;
        fs::rename(&temporary, path)
            .map_err(|_| support_error("support source cannot be published"))
    })();
    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

#[cfg(unix)]
fn set_private_support_directory_permissions(path: &Path) -> std::io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o700))
}

#[cfg(not(unix))]
fn set_private_support_directory_permissions(_path: &Path) -> std::io::Result<()> {
    Ok(())
}

impl SupportBundleCollector for FileSupportBundleCollector {
    fn collect_support_bundle(
        &mut self,
        request: SupportBundleRequest,
    ) -> Result<SupportBundleReport, AppError> {
        if self
            .offline_lock
            .as_ref()
            .is_some_and(|lock| lock.state() != DataDirectoryLockState::HeldExclusive)
        {
            return Err(AppError::new(
                ErrorCode::DataDirectoryLockStateInvalid,
                "offline support bundle lost its exclusive data lock",
            ));
        }
        let parent = self.output.parent().ok_or_else(|| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive has no parent directory",
            )
        })?;
        let parent_metadata = fs::symlink_metadata(parent).map_err(|_| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive parent is unavailable",
            )
        })?;
        let output_is_safe = match self.output.symlink_metadata() {
            Ok(metadata) => metadata.is_file() && !metadata.file_type().is_symlink(),
            Err(error) => error.kind() == std::io::ErrorKind::NotFound,
        };
        if !parent_metadata.is_dir() || parent_metadata.file_type().is_symlink() || !output_is_safe
        {
            return Err(AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive output is unsafe",
            ));
        }
        let temporary = self.output.with_extension("tmp");
        if temporary.symlink_metadata().is_ok() {
            return Err(AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive temporary path is unsafe",
            ));
        }
        let file = OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&temporary)
            .map_err(|_| {
                AppError::new(
                    ErrorCode::SupportBundleReportInvalid,
                    "support archive cannot be created",
                )
            })?;
        let mut archive = tar::Builder::new(file);
        let mut artifacts = Vec::new();
        let mut omissions = Vec::new();
        let mut total_bytes = 0_u64;
        let mut oldest_log_age_seconds = None;
        for artifact in request.artifacts {
            if artifacts.contains(&artifact) {
                continue;
            }
            let (relative, archive_name) = Self::source_for(artifact);
            let path = self.root.join(relative);
            let metadata = match fs::symlink_metadata(&path) {
                Ok(metadata) if metadata.is_file() && !metadata.file_type().is_symlink() => {
                    metadata
                }
                _ => {
                    omissions.push(SupportBundleOmission {
                        artifact,
                        reason: SupportBundleOmissionReason::NotAvailable,
                    });
                    continue;
                }
            };
            let age = if artifact == SupportBundleArtifact::BoundedProductLog {
                metadata
                    .modified()
                    .ok()
                    .and_then(|time| SystemTime::now().duration_since(time).ok())
                    .map(|duration| duration.as_secs())
            } else {
                None
            };
            if artifacts.len() >= usize::from(request.bounds.max_files)
                || total_bytes.saturating_add(metadata.len()) > request.bounds.max_total_bytes
                || age.is_some_and(|value| value > request.bounds.max_log_age_seconds)
            {
                omissions.push(SupportBundleOmission {
                    artifact,
                    reason: SupportBundleOmissionReason::ExceededCollectionBounds,
                });
                continue;
            }
            let mut input = open_regular_no_follow(&path).map_err(|_| {
                AppError::new(
                    ErrorCode::SupportBundleReportInvalid,
                    "support artifact cannot be opened",
                )
            })?;
            let mut content = Vec::with_capacity(metadata.len() as usize);
            input.read_to_end(&mut content).map_err(|_| {
                AppError::new(
                    ErrorCode::SupportBundleReportInvalid,
                    "support artifact cannot be read",
                )
            })?;
            if contains_sensitive_content(&content) {
                let _ = fs::remove_file(&temporary);
                return Err(AppError::new(
                    ErrorCode::SupportBundleReportInvalid,
                    "support artifact redaction scan failed",
                ));
            }
            let mut header = tar::Header::new_gnu();
            header.set_size(content.len() as u64);
            header.set_mode(0o600);
            header.set_cksum();
            archive
                .append_data(&mut header, archive_name, content.as_slice())
                .map_err(|_| {
                    AppError::new(
                        ErrorCode::SupportBundleReportInvalid,
                        "support archive write failed",
                    )
                })?;
            total_bytes += metadata.len();
            artifacts.push(artifact);
            if let Some(value) = age {
                oldest_log_age_seconds = Some(value);
            }
        }
        let manifest = format!(
            "format=sponzey-support-v1\nartifacts={}\nredaction=passed\n",
            artifacts.len()
        );
        let mut header = tar::Header::new_gnu();
        header.set_size(manifest.len() as u64);
        header.set_mode(0o600);
        header.set_cksum();
        archive
            .append_data(&mut header, "manifest.txt", manifest.as_bytes())
            .map_err(|_| {
                AppError::new(
                    ErrorCode::SupportBundleReportInvalid,
                    "support manifest write failed",
                )
            })?;
        archive.finish().map_err(|_| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive finalization failed",
            )
        })?;
        drop(archive);
        crate::set_private_file_permissions(&temporary).map_err(|_| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive permissions failed",
            )
        })?;
        let bytes = fs::read(&temporary).map_err(|_| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive cannot be hashed",
            )
        })?;
        let digest: [u8; 32] = Sha256::digest(&bytes).into();
        fs::rename(&temporary, &self.output).map_err(|_| {
            AppError::new(
                ErrorCode::SupportBundleReportInvalid,
                "support archive cannot be published",
            )
        })?;
        Ok(SupportBundleReport {
            archive: SupportBundleArchiveReceipt {
                archive_id: crate::hex_encode_bytes(&digest),
                digest_sha256: digest,
                redaction_applied: true,
            },
            collected_artifacts: artifacts,
            total_bytes,
            oldest_collected_log_age_seconds: oldest_log_age_seconds,
            omissions,
        })
    }
}

fn contains_sensitive_content(bytes: &[u8]) -> bool {
    let content = String::from_utf8_lossy(bytes).to_ascii_lowercase();
    [
        "-----begin private key",
        "authorization:",
        "cookie:",
        "set-cookie:",
        "password=",
        "secret=",
    ]
    .iter()
    .any(|needle| content.contains(needle))
}

#[cfg(unix)]
fn open_regular_no_follow(path: &Path) -> std::io::Result<File> {
    use std::os::unix::fs::OpenOptionsExt;

    OpenOptions::new()
        .read(true)
        .custom_flags(libc::O_NOFOLLOW)
        .open(path)
}

#[cfg(not(unix))]
fn open_regular_no_follow(path: &Path) -> std::io::Result<File> {
    File::open(path)
}

#[cfg(test)]
mod tests {
    use super::*;
    use edge_domain::SupportBundleBounds;
    use std::time::{SystemTime, UNIX_EPOCH};

    fn root(label: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("edge-support-{label}-{unique}"));
        fs::create_dir_all(&path).unwrap();
        path
    }

    fn request(artifact: SupportBundleArtifact) -> SupportBundleRequest {
        SupportBundleRequest {
            artifacts: vec![artifact],
            bounds: SupportBundleBounds::SAFE_DEFAULT,
        }
    }

    #[test]
    fn publishes_only_allowlisted_sources_with_private_permissions() {
        let root = root("publish-sources");
        let collector = FileSupportBundleCollector::new_online(&root, root.join("bundle.tar"));
        collector
            .publish_sources(&[
                (
                    SupportBundleArtifact::VersionManifest,
                    b"version = \"test\"\n".to_vec(),
                ),
                (
                    SupportBundleArtifact::BoundedProductLog,
                    b"{\"event\":\"test\"}\n".to_vec(),
                ),
            ])
            .unwrap();
        assert!(root.join("version.manifest").is_file());
        assert!(root.join("logs/product.log").is_file());
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            assert_eq!(
                fs::metadata(&root).unwrap().permissions().mode() & 0o777,
                0o700
            );
            assert_eq!(
                fs::metadata(root.join("logs"))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o700
            );
            assert_eq!(
                fs::metadata(root.join("version.manifest"))
                    .unwrap()
                    .permissions()
                    .mode()
                    & 0o777,
                0o600
            );
        }
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn source_publishing_rejects_symlinked_subdirectory_before_writing_any_source() {
        use std::os::unix::fs::symlink;
        let root = root("source-symlink");
        let outside = root.join("outside");
        let support = root.join("support");
        fs::create_dir(&outside).unwrap();
        fs::create_dir(&support).unwrap();
        symlink(&outside, support.join("config")).unwrap();
        let collector =
            FileSupportBundleCollector::new_online(&support, support.join("bundle.tar"));
        let result = collector.publish_sources(&[
            (
                SupportBundleArtifact::VersionManifest,
                b"version = \"test\"\n".to_vec(),
            ),
            (
                SupportBundleArtifact::MaskedConfig,
                b"routes = 0\n".to_vec(),
            ),
        ]);
        assert!(result.is_err());
        assert!(!support.join("version.manifest").exists());
        assert!(!outside.join("masked.toml").exists());
        let _ = fs::remove_dir_all(root);
    }

    #[derive(Debug)]
    struct Guard(DataDirectoryLockState);

    impl DataDirectoryLockGuard for Guard {
        fn state(&self) -> DataDirectoryLockState {
            self.0
        }
        fn release(&mut self) -> Result<(), AppError> {
            Ok(())
        }
    }

    #[test]
    fn rejects_secret_bearing_fixture_before_archive_publication() {
        let root = root("secret");
        fs::write(root.join("version.manifest"), "-----BEGIN PRIVATE KEY-----").unwrap();
        let output = root.join("bundle.tar");
        let error = FileSupportBundleCollector::new_online(&root, &output)
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest))
            .unwrap_err();
        assert_eq!(error.code, ErrorCode::SupportBundleReportInvalid);
        assert!(!output.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn replaces_previous_archive_only_after_new_collection_succeeds() {
        let root = root("replace");
        let source = root.join("version.manifest");
        let output = root.join("bundle.tar");
        fs::write(&source, "version=first").unwrap();
        let mut collector = FileSupportBundleCollector::new_online(&root, &output);
        let first = collector
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest))
            .unwrap();
        let previous = fs::read(&output).unwrap();
        fs::write(&source, "-----BEGIN PRIVATE KEY-----").unwrap();
        assert!(collector
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest))
            .is_err());
        assert_eq!(fs::read(&output).unwrap(), previous);
        fs::write(&source, "version=second").unwrap();
        let second = collector
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest))
            .unwrap();
        assert_ne!(first.archive.digest_sha256, second.archive.digest_sha256);
        let file = File::open(&output).unwrap();
        let mut archive = tar::Archive::new(file);
        let mut contents = String::new();
        archive
            .entries()
            .unwrap()
            .next()
            .unwrap()
            .unwrap()
            .read_to_string(&mut contents)
            .unwrap();
        assert_eq!(contents, "version=second");
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn refuses_existing_output_symlink_without_modifying_its_target() {
        use std::os::unix::fs::symlink;
        let root = root("output-symlink");
        let target = root.join("target");
        let output = root.join("bundle.tar");
        fs::write(&target, "original").unwrap();
        symlink(&target, &output).unwrap();
        let result = FileSupportBundleCollector::new_online(&root, &output)
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest));
        assert!(result.is_err());
        assert_eq!(fs::read_to_string(&target).unwrap(), "original");
        assert!(fs::symlink_metadata(output)
            .unwrap()
            .file_type()
            .is_symlink());
        let _ = fs::remove_dir_all(root);
    }

    #[cfg(unix)]
    #[test]
    fn omits_symlinked_artifact_without_reading_its_target() {
        use std::os::unix::fs::symlink;
        let root = root("symlink");
        let outside = root.join("outside");
        fs::write(&outside, "safe outside content").unwrap();
        symlink(&outside, root.join("version.manifest")).unwrap();
        let output = root.join("bundle.tar");
        let report = FileSupportBundleCollector::new_online(&root, &output)
            .collect_support_bundle(request(SupportBundleArtifact::VersionManifest))
            .unwrap();
        assert!(report.collected_artifacts.is_empty());
        assert_eq!(
            report.omissions[0].reason,
            SupportBundleOmissionReason::NotAvailable
        );
        assert!(output.exists());
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn omits_an_artifact_that_exceeds_the_requested_byte_bound() {
        let root = root("bound");
        fs::write(root.join("version.manifest"), "two bytes").unwrap();
        let output = root.join("bundle.tar");
        let report = FileSupportBundleCollector::new_online(&root, &output)
            .collect_support_bundle(SupportBundleRequest {
                artifacts: vec![SupportBundleArtifact::VersionManifest],
                bounds: SupportBundleBounds {
                    max_files: 1,
                    max_total_bytes: 1,
                    max_log_age_seconds: 1,
                },
            })
            .unwrap();
        assert!(report.collected_artifacts.is_empty());
        assert_eq!(
            report.omissions[0].reason,
            SupportBundleOmissionReason::ExceededCollectionBounds
        );
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn offline_collection_requires_an_exclusive_data_lock() {
        let root = root("lock");
        let error = FileSupportBundleCollector::new_offline(
            &root,
            root.join("bundle.tar"),
            Box::new(Guard(DataDirectoryLockState::Released)),
        )
        .unwrap_err();
        assert_eq!(error.code, ErrorCode::DataDirectoryLockStateInvalid);
        let _ = fs::remove_dir_all(root);
    }

    #[test]
    fn omits_a_product_log_older_than_the_requested_bound() {
        let root = root("old-log");
        let logs = root.join("logs");
        fs::create_dir(&logs).unwrap();
        let log = logs.join("product.log");
        fs::write(&log, "safe log line").unwrap();
        filetime::set_file_mtime(&log, filetime::FileTime::from_unix_time(1, 0)).unwrap();
        let output = root.join("bundle.tar");
        let report = FileSupportBundleCollector::new_online(&root, &output)
            .collect_support_bundle(SupportBundleRequest {
                artifacts: vec![SupportBundleArtifact::BoundedProductLog],
                bounds: SupportBundleBounds {
                    max_files: 1,
                    max_total_bytes: 1024,
                    max_log_age_seconds: 1,
                },
            })
            .unwrap();
        assert!(report.collected_artifacts.is_empty());
        assert_eq!(
            report.omissions[0].reason,
            SupportBundleOmissionReason::ExceededCollectionBounds
        );
        let _ = fs::remove_dir_all(root);
    }
}
