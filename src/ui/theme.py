"""Shared Twano visual design system."""

from __future__ import annotations

from PySide6.QtWidgets import QAbstractItemView, QTableWidget


APP_STYLESHEET = """
QMainWindow, QWidget {
    background-color: #0b121a;
    color: #e6ebef;
    font-family: "Segoe UI";
    font-size: 16px;
}

#sidebar {
    background-color: #0d1722;
    border-right: 1px solid #223445;
}
#brandIcon {
    background: transparent;
    color: #55a9ff;
}
#appName {
    background: transparent;
    color: #f5e5c5;
    font-family: "Georgia";
    font-weight: 700;
    letter-spacing: 0.4px;
}
#appSubtitle { background: transparent; color: #d6c3a5; }
#navigation {
    background: transparent;
    border: none;
    color: #e6edf5;
    outline: none;
}
#navigation::item {
    padding-left: 13px;
    padding-right: 10px;
    margin: 0;
    border-radius: 7px;
}
#navigation::item:selected {
    background-color: #205eae;
    color: #ffffff;
    border: 1px solid #2f75c9;
}
#navigation::item:hover:!selected {
    background-color: #1b2b3a;
    color: #ffffff;
}
#navigationDivider {
    color: #314455;
    background: transparent;
    border: none;
    border-top: 1px solid #314455;
}
#protectionPanel {
    background-color: #182635;
    border: 1px solid #31485c;
    border-radius: 7px;
}
#protectionPanel:hover { border-color: #46647d; }
#protectionIcon { background: transparent; color: #8fd56c; }
#protectionLabel {
    background: transparent;
    color: #f2f6fa;
    border: none;
    padding: 0;
    font-weight: 600;
}
#protectionDetail {
    background: transparent;
    color: #96a9ba;
    border: none;
    padding: 0;
}
#versionLabel { background: transparent; color: #71879a; }
#checkUpdatesAction {
    background-color: #15283a;
    color: #dce9f0;
    border: 1px solid #355c73;
    border-radius: 6px;
    padding: 5px 10px;
    text-align: left;
    font-weight: 600;
}
#checkUpdatesAction:hover {
    background-color: #213746;
    border-color: #4e7890;
}
#checkUpdatesAction:pressed {
    background-color: #102131;
    padding: 7px 8px 3px 12px;
    border-style: inset;
}
#applicationStatusBar {
    background-color: #0a1118;
    color: #c4d0da;
    border-top: 1px solid #263746;
    min-height: 36px;
}
#applicationStatusBar::item { border: none; }
#statusLibrary, #statusBookCount, #statusVersion {
    background: transparent;
    color: #bdc9d2;
    padding: 0 8px;
    font-size: 12px;
}
#statusSeparator {
    color: #344654;
    background: #344654;
    min-width: 1px;
    max-width: 1px;
    margin: 8px 2px;
}
#footerUpdateAction {
    background: transparent;
    color: #8ebde5;
    border: 1px solid #2d4c63;
    border-radius: 5px;
    padding: 3px 9px;
    margin: 3px 7px;
    min-height: 18px;
    font-size: 11px;
    font-weight: 600;
}
#footerUpdateAction:hover {
    background-color: #172a39;
    border-color: #47728f;
    color: #dcecf8;
}
#footerUpdateAction:pressed {
    background-color: #101f2b;
    padding: 5px 7px 1px 11px;
    border-style: inset;
}
#statusReady {
    background: transparent;
    color: #91d566;
    padding: 0 10px 0 2px;
    font-size: 13px;
}
QPushButton:focus, QComboBox:focus, QLineEdit:focus,
QListWidget:focus, QTableWidget:focus, QTextEdit:focus {
    border: 2px solid #77bfff;
}
#metadataReviewPanel, #healthScorePanel, #healthIssueCard,
#guidancePanel {
    background-color: #101a24;
    border: 1px solid #2d4255;
    border-radius: 7px;
}
#metadataCandidateList {
    background-color: #0f1821;
    border: 1px solid #304657;
    border-radius: 6px;
}
#metadataCandidateList::item {
    padding: 8px;
    border-bottom: 1px solid #253745;
}
#metadataCandidateList::item:selected {
    background-color: #205eae;
    color: #ffffff;
}
#metadataCoverPreview {
    background-color: #173348;
    color: #a8c4d7;
    border: 1px solid #3c6077;
    border-radius: 6px;
}
#metadataPlanSummary, #metadataStatus, #duplicateStatus, #pluginStatus {
    color: #b8c9d5;
}
#metadataLookupAction, #metadataPreviewAction, #coverSearchAction,
#coverSearchOnlyAction,
#duplicateRefreshAction,
#healthRefreshAction, #calibreDetectAction, #networkCheckAction {
    background-color: #236f91;
    border-color: #5199ba;
    color: #ffffff;
}
#metadataApplyAction, #coverDownloadAction, #pluginInstallAction,
#pluginEnableAction, #calibreAddSourceAction, #networkAddSourceAction {
    background-color: #2d7f46;
    border-color: #58ad73;
    color: #ffffff;
}
#metadataQueueAction, #coverFileAction, #duplicatePreferredAction,
#pluginPackageAction, #calibreBrowseAction {
    background-color: #674fb2;
    border-color: #927dd2;
    color: #ffffff;
}
#duplicateKeepAction, #duplicateLibraryAction, #pluginSourceAction,
#calibreOpenAction, #calibreInspectAction {
    background-color: #177b83;
    border-color: #42aab1;
    color: #ffffff;
}
#duplicateQuarantineAction, #pluginDisableAction {
    background-color: #9a641c;
    border-color: #cf963f;
    color: #ffffff;
}
#pluginInstallAction:disabled,
#pluginEnableAction:disabled,
#pluginDisableAction:disabled,
#pluginSourceAction:disabled,
#pluginPackageAction:disabled {
    color: #667682;
    background-color: #1a232b;
    border-color: #2b3741;
}
#quarantineRestoreAction {
    background-color: #2d7f46;
    border-color: #58ad73;
    color: #ffffff;
}
#healthScore {
    color: #8fd56c;
    font-size: 38px;
    font-weight: 700;
    min-width: 80px;
}
#healthScoreText, #healthIssueDescription, #healthEmpty, #guideStep {
    color: #aebfca;
}
#healthIssuePreview {
    color: #d8e4eb;
    padding-top: 8px;
}
#healthIssueTitle {
    color: #edf3f7;
    font-size: 17px;
    font-weight: 700;
}
#healthCount_information, #healthCount_warning, #healthCount_urgent {
    min-width: 38px;
    font-size: 20px;
    font-weight: 700;
}
#healthCount_information { color: #69b7ff; }
#healthCount_warning { color: #e2bb75; }
#healthCount_urgent { color: #ef7868; }
#pageTitle { font-size: 30px; font-weight: 700; color: #edf2f5; }
#pageDescription { color: #a8b6c2; font-size: 16px; }
QTabWidget::pane {
    background-color: #0d151d;
    border: 1px solid #304354;
    border-radius: 6px;
    top: -1px;
}
QTabBar::tab {
    background-color: #18232d;
    color: #aebdca;
    border: 1px solid #304354;
    padding: 8px 18px;
    min-width: 120px;
}
QTabBar::tab:selected {
    background-color: #205eae;
    color: #ffffff;
    border-color: #4c94dc;
}
QTabBar::tab:hover:!selected {
    background-color: #223441;
    color: #ffffff;
}
#searchFilters {
    background-color: #101a24;
    border: 1px solid #2d4255;
    border-radius: 6px;
}
#filterLabel {
    background: transparent;
    color: #8fa4b4;
    font-size: 12px;
    font-weight: 600;
}
#searchResultsScroll, #reviewQueueScroll {
    background: transparent;
    border: none;
}
#searchResultsScroll > QWidget > QWidget,
#reviewQueueScroll > QWidget > QWidget {
    background: transparent;
}
#searchResultItem {
    background-color: #101a24;
    border: 1px solid #2d4255;
    border-radius: 6px;
}
#searchResultItem:hover { border-color: #41647c; }
#resultCover {
    background-color: #285d7c;
    color: #ffffff;
    border: 1px solid #4b7d99;
    border-radius: 2px;
    font-size: 17px;
    font-weight: 700;
}
#resultTitle {
    background: transparent;
    color: #f0f5f8;
    font-size: 18px;
    font-weight: 700;
}
#resultByline {
    background: transparent;
    color: #bdcbd5;
    font-size: 15px;
}
#resultSeries, #resultFacts {
    background: transparent;
    color: #8fb7d1;
    font-size: 13px;
}
#resultLocation {
    background: transparent;
    color: #8396a5;
    font-size: 12px;
}
#resultIssues {
    background: transparent;
    color: #e2bb75;
    font-size: 13px;
}
#resultOpen, #resultView {
    background-color: #1a3344;
    color: #dce9f0;
    border: 1px solid #355c73;
    border-radius: 4px;
    padding: 6px 10px;
}
#resultOpen:hover, #resultView:hover { background-color: #23475d; }
#resultOpen:pressed, #resultView:pressed {
    background-color: #142b3b;
    padding: 8px 8px 4px 12px;
    border-style: inset;
}
#emptyResults {
    background-color: #101a24;
    color: #aabac5;
    border: 1px solid #2d4255;
    border-radius: 6px;
    padding: 22px;
}

QPushButton {
    background-color: #202c36; color: #dce5eb; border: 1px solid #3b4b58;
    border-radius: 6px; padding: 10px 16px; min-height: 24px; font-size: 15px;
}
QPushButton:hover { background-color: #283743; border-color: #587086; }
QPushButton:pressed {
    background-color: #1c2730;
    border-style: inset;
    padding: 12px 14px 8px 18px;
}
QPushButton:checked {
    background-color: #205eae;
    color: #ffffff;
    border-color: #4c94dc;
}
QPushButton:disabled { color: #667682; background-color: #1a232b; border-color: #2b3741; }
#primaryButton { background-color: #2878c8; color: #ffffff; border: none; font-weight: 600; }
#primaryButton:hover { background-color: #2168ae; }

#protectionPolicyPanel {
    background-color: #101a24;
    border: 1px solid #2d4255;
    border-radius: 7px;
}
#fieldLabel {
    color: #8fa4b4;
    font-size: 13px;
    font-weight: 600;
}
#protectedPath {
    color: #c7d6e0;
    background-color: #11181e;
    border: 1px solid #334757;
    border-radius: 5px;
    padding: 8px 10px;
}
#sectionTitle {
    color: #edf2f5;
    font-size: 20px;
    font-weight: 700;
}
#sectionDescription, #futureProtectionNote {
    color: #9fb0bd;
    font-size: 14px;
}
#futureProtectionNote {
    background-color: #162330;
    border: 1px solid #30485c;
    border-radius: 6px;
    padding: 9px 12px;
}
#backupStatus {
    color: #bfd0dc;
    min-height: 24px;
}
#changePlanPanel {
    background-color: #101a24;
    border: 1px solid #365066;
    border-radius: 7px;
}
#changePlanTitle {
    color: #f0f5f8;
    font-size: 18px;
    font-weight: 700;
}
#changePlanFacts {
    color: #91b9d3;
    font-size: 13px;
}
#changePlanDetails {
    background-color: #11181e;
    color: #cbd8e1;
    border: 1px solid #334757;
    border-radius: 5px;
    padding: 8px;
}
#historyStatus {
    color: #bfd0dc;
    min-height: 24px;
}
#browseBackupAction,
#saveBackupPolicyAction,
#createBackupAction,
#verifyBackupAction,
#restoreBackupAction,
#reviewOldBackupsAction,
#cancelBackupAction,
#previewPlanAction,
#previewReversibleAction,
#previewUndoAction,
#approvePlanAction,
#applyPlanAction,
#cancelPlanAction,
#refreshHistoryAction,
#exportReportAction {
    color: #ffffff;
    font-weight: 600;
}
#browseBackupAction {
    background-color: #236f91;
    border-color: #5199ba;
}
#browseBackupAction:hover {
    background-color: #2c82a7;
    border-color: #75b1cc;
}
#saveBackupPolicyAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#saveBackupPolicyAction:hover {
    background-color: #7961c4;
    border-color: #aa98df;
}
#createBackupAction {
    background-color: #2d7f46;
    border-color: #58ad73;
}
#createBackupAction:hover {
    background-color: #389456;
    border-color: #7ac18f;
}
#verifyBackupAction {
    background-color: #177b83;
    border-color: #42aab1;
}
#verifyBackupAction:hover {
    background-color: #218f98;
    border-color: #67c0c5;
}
#restoreBackupAction {
    background-color: #9a641c;
    border-color: #cf963f;
}
#restoreBackupAction:hover {
    background-color: #ad7628;
    border-color: #e0ab5b;
}
#reviewOldBackupsAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#reviewOldBackupsAction:hover {
    background-color: #7961c4;
    border-color: #aa98df;
}
#cancelBackupAction {
    background-color: #a44c32;
    border-color: #d1795e;
}
#cancelBackupAction:hover {
    background-color: #bb5a3d;
    border-color: #e3947d;
}
#previewPlanAction {
    background-color: #2878c8;
    border-color: #4f9be5;
}
#previewPlanAction:hover {
    background-color: #3489da;
    border-color: #72b4ef;
}
#previewReversibleAction {
    background-color: #177b83;
    border-color: #42aab1;
}
#previewReversibleAction:hover {
    background-color: #218f98;
    border-color: #67c0c5;
}
#previewUndoAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#previewUndoAction:hover {
    background-color: #7961c4;
    border-color: #aa98df;
}
#approvePlanAction {
    background-color: #9a641c;
    border-color: #cf963f;
}
#approvePlanAction:hover {
    background-color: #ad7628;
    border-color: #e0ab5b;
}
#applyPlanAction {
    background-color: #2d7f46;
    border-color: #58ad73;
}
#applyPlanAction:hover {
    background-color: #389456;
    border-color: #7ac18f;
}
#cancelPlanAction {
    background-color: #80516f;
    border-color: #ae7b99;
}
#cancelPlanAction:hover {
    background-color: #956180;
    border-color: #c495af;
}
#refreshHistoryAction {
    background-color: #177b83;
    border-color: #42aab1;
}
#refreshHistoryAction:hover {
    background-color: #218f98;
    border-color: #67c0c5;
}
#exportReportAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#exportReportAction:hover {
    background-color: #7961c4;
    border-color: #aa98df;
}
#browseBackupAction:pressed { background-color: #1b5b73; }
#saveBackupPolicyAction:pressed { background-color: #51408e; }
#createBackupAction:pressed { background-color: #246738; }
#verifyBackupAction:pressed { background-color: #12646b; }
#restoreBackupAction:pressed { background-color: #7d5016; }
#reviewOldBackupsAction:pressed { background-color: #51408e; }
#cancelBackupAction:pressed { background-color: #843d29; }
#previewPlanAction:pressed { background-color: #1f64a8; }
#previewReversibleAction:pressed { background-color: #12646b; }
#previewUndoAction:pressed { background-color: #51408e; }
#approvePlanAction:pressed { background-color: #7d5016; }
#applyPlanAction:pressed { background-color: #246738; }
#cancelPlanAction:pressed { background-color: #67415a; }
#refreshHistoryAction:pressed { background-color: #12646b; }
#exportReportAction:pressed { background-color: #51408e; }
#browseBackupAction:disabled,
#saveBackupPolicyAction:disabled,
#createBackupAction:disabled,
#verifyBackupAction:disabled,
#restoreBackupAction:disabled,
#reviewOldBackupsAction:disabled,
#cancelBackupAction:disabled,
#previewPlanAction:disabled,
#previewReversibleAction:disabled,
#previewUndoAction:disabled,
#approvePlanAction:disabled,
#applyPlanAction:disabled,
#cancelPlanAction:disabled,
#refreshHistoryAction:disabled,
#exportReportAction:disabled {
    color: #667682;
    background-color: #1a232b;
    border-color: #2b3741;
}
#approvePlanAction:disabled {
    color: #c2b18b;
    background-color: #2c281f;
    border-color: #665938;
}

#openBookAction,
#openFolderAction,
#viewMetadataAction,
#reviewIssuesAction,
#manageCollectionsAction {
    color: #ffffff;
    font-weight: 600;
}
#openBookAction {
    background-color: #2878c8;
    border-color: #4f9be5;
}
#openBookAction:hover { background-color: #3489da; border-color: #72b4ef; }
#openBookAction:pressed { background-color: #1f64a8; }
#openFolderAction {
    background-color: #177b83;
    border-color: #42aab1;
}
#openFolderAction:hover { background-color: #218f98; border-color: #67c0c5; }
#openFolderAction:pressed { background-color: #12646b; }
#viewMetadataAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#viewMetadataAction:hover { background-color: #7961c4; border-color: #aa98df; }
#viewMetadataAction:pressed { background-color: #51408e; }
#reviewIssuesAction {
    background-color: #9a641c;
    border-color: #cf963f;
}
#reviewIssuesAction:hover { background-color: #ad7628; border-color: #e0ab5b; }
#reviewIssuesAction:pressed { background-color: #7d5016; }
#manageCollectionsAction {
    background-color: #2d7848;
    border-color: #58a875;
}
#manageCollectionsAction:hover {
    background-color: #388b57;
    border-color: #79bd91;
}
#manageCollectionsAction:pressed { background-color: #245f3a; }
#openBookAction:disabled,
#openFolderAction:disabled,
#viewMetadataAction:disabled,
#reviewIssuesAction:disabled,
#manageCollectionsAction:disabled {
    color: #667682;
    background-color: #1a232b;
    border-color: #2b3741;
}

#addSourceAction,
#editSourceAction,
#testConnectionAction,
#toggleSourceAction,
#removeWatchAction,
#previewScanAction,
#previewAllSourcesAction,
#cancelScanAction,
#discardPreviewAction,
#applyPreviewAction {
    color: #ffffff;
    font-weight: 600;
}
#addSourceAction {
    background-color: #237269;
    border-color: #4ca79c;
}
#addSourceAction:hover { background-color: #2d877c; border-color: #70bdb4; }
#editSourceAction {
    background-color: #674fb2;
    border-color: #927dd2;
}
#editSourceAction:hover { background-color: #7961c4; border-color: #aa98df; }
#testConnectionAction {
    background-color: #236f91;
    border-color: #5199ba;
}
#testConnectionAction:hover {
    background-color: #2c82a7;
    border-color: #75b1cc;
}
#toggleSourceAction {
    background-color: #8d661f;
    border-color: #bf9445;
}
#toggleSourceAction:hover {
    background-color: #a17829;
    border-color: #d1aa62;
}
#removeWatchAction {
    background-color: #943f4c;
    border-color: #c66b77;
}
#removeWatchAction:hover {
    background-color: #aa4a59;
    border-color: #da8791;
}
#previewScanAction {
    background-color: #2878c8;
    border-color: #4f9be5;
}
#previewScanAction:hover {
    background-color: #3489da;
    border-color: #72b4ef;
}
#previewAllSourcesAction {
    background-color: #2878c8;
    border-color: #4f9be5;
}
#previewAllSourcesAction:hover {
    background-color: #3489da;
    border-color: #72b4ef;
}
#cancelScanAction {
    background-color: #a44c32;
    border-color: #d1795e;
}
#cancelScanAction:hover {
    background-color: #bb5a3d;
    border-color: #e3947d;
}
#discardPreviewAction {
    background-color: #80516f;
    border-color: #ae7b99;
}
#discardPreviewAction:hover {
    background-color: #956180;
    border-color: #c495af;
}
#applyPreviewAction {
    background-color: #2d7f46;
    border-color: #58ad73;
}
#applyPreviewAction:hover {
    background-color: #389456;
    border-color: #7ac18f;
}
#addSourceAction:pressed,
#testConnectionAction:pressed { background-color: #1b5b55; }
#editSourceAction:pressed { background-color: #51408e; }
#toggleSourceAction:pressed { background-color: #725119; }
#removeWatchAction:pressed { background-color: #77333d; }
#previewScanAction:pressed { background-color: #1f64a8; }
#previewAllSourcesAction:pressed { background-color: #1f64a8; }
#cancelScanAction:pressed { background-color: #843d29; }
#discardPreviewAction:pressed { background-color: #67415a; }
#applyPreviewAction:pressed { background-color: #246738; }
#addSourceAction:disabled,
#editSourceAction:disabled,
#testConnectionAction:disabled,
#toggleSourceAction:disabled,
#removeWatchAction:disabled,
#previewScanAction:disabled,
#previewAllSourcesAction:disabled,
#cancelScanAction:disabled,
#discardPreviewAction:disabled,
#applyPreviewAction:disabled {
    color: #667682;
    background-color: #1a232b;
    border-color: #2b3741;
}

QLineEdit, QComboBox, QSpinBox, QTextEdit {
    background-color: #11181e; color: #e5edf2; border: 1px solid #40515f;
    border-radius: 6px; padding: 9px 11px; font-size: 15px; selection-background-color: #2878c8;
}
QLineEdit:focus, QComboBox:focus, QSpinBox:focus, QTextEdit:focus {
    border-color: #4ca3e6;
}
QComboBox QAbstractItemView {
    background-color: #1d2730; color: #e5edf2; border: 1px solid #40515f;
    selection-background-color: #2878c8; selection-color: #ffffff;
}

QTableWidget, QTableView, #libraryGrid {
    background-color: #182129;
    alternate-background-color: #202a33;
    color: #e7eef3;
    gridline-color: #32404b;
    border: 1px solid #354550;
    border-radius: 5px;
    selection-background-color: #2878c8;
    selection-color: #ffffff;
    outline: none;
}
QTableWidget::item, QTableView::item {
    padding: 5px 7px;
    border: none;
}
QTableWidget::item:hover:!selected, QTableView::item:hover:!selected {
    background-color: #2a3742;
    color: #ffffff;
}
QTableWidget::item:selected, QTableView::item:selected {
    background-color: #2878c8;
    color: #ffffff;
}
#libraryGrid {
    border-radius: 6px;
    padding: 5px;
}
#bookDetails {
    background-color: #101a24;
    border: 1px solid #2d4255;
    border-radius: 7px;
}
#bookDetails QScrollArea,
#bookDetails QScrollArea > QWidget > QWidget {
    background: transparent;
    border: none;
}
#detailsCover {
    background-color: #183449;
    color: #aac4d5;
    border: 1px solid #41647c;
    border-radius: 4px;
    font-size: 13px;
    font-weight: 700;
}
#detailsTitle {
    color: #f2f6f9;
    font-size: 21px;
    font-weight: 700;
}
#detailsAuthor {
    color: #c0cdd6;
    font-size: 16px;
}
#detailsSeries {
    color: #8fc1df;
    font-size: 14px;
}
#detailsDescription {
    color: #b3c0ca;
    font-size: 14px;
}
#detailsFacts, #detailsCollections {
    color: #91a7b7;
    font-size: 13px;
}
#detailsIssues {
    color: #e2bb75;
    font-size: 13px;
}
QHeaderView::section {
    background-color: #25313b; color: #dce6ec; border: none;
    border-right: 1px solid #3a4955; border-bottom: 1px solid #435461;
    padding: 7px 7px; font-weight: 600;
}
QHeaderView::section:hover { background-color: #2c3a46; }
QTableCornerButton::section { background-color: #25313b; border: none; }

QProgressBar {
    background-color: #11181e; color: #e8f1f6; border: 1px solid #384955;
    border-radius: 5px; text-align: center; min-height: 18px;
}
QProgressBar::chunk { background-color: #2e9f55; border-radius: 4px; }

QScrollBar:vertical { background: #151b21; width: 10px; margin: 0; }
QScrollBar::handle:vertical { background: #40515e; min-height: 28px; border-radius: 5px; }
QScrollBar::handle:vertical:hover { background: #526674; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: #151b21; height: 10px; margin: 0; }
QScrollBar::handle:horizontal { background: #40515e; min-width: 28px; border-radius: 5px; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
"""


def configure_table(table: QTableWidget, row_height: int = 29) -> None:
    """Apply consistent behaviour to a Twano data table."""
    table.setAlternatingRowColors(True)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setShowGrid(True)
    table.setWordWrap(False)
    table.verticalHeader().setVisible(False)
    table.verticalHeader().setDefaultSectionSize(row_height)
    table.horizontalHeader().setHighlightSections(False)
