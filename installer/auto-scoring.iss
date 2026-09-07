; Inno Setup script for the Auto-Scoring Windows installer (Issue #24).
;
; Build it with `pnpm run package:installer`, which expects both halves of the
; app to have been built first:
;
;   pnpm run package:sidecar   -> backend/dist/auto-scoring-sidecar/
;   flutter build windows --release (in app/) -> app/build/windows/x64/runner/Release/
;
; Why Inno Setup and not MSIX -- which docs/technology-stack.md §4 named as the
; first choice, and which this issue asked to try first: an MSIX package cannot
; be installed at all unless it is signed by a certificate the target machine
; trusts. No code-signing certificate exists for this project yet, and buying
; one is explicitly out of scope (Issue #24 対象外). That makes the acceptance
; criterion "produce an unsigned test artifact, and keep the signing step
; separate as a human-only task" impossible to satisfy with MSIX: the unsigned
; artifact would be a file nobody can install or smoke-test. An unsigned Inno
; Setup .exe installs after a SmartScreen warning, so CI can build one and a
; human can run it on a clean VM today. Two further mismatches are recorded in
; docs/windows-distribution.md §2; the decision is reversible once a
; certificate exists.

#define AppName "Auto-Scoring"
#define AppPublisher "Auto-Scoring"
; Keep in step with `version:` in app/pubspec.yaml.
#define AppVersion "1.0.0"
#define AppExeName "auto_scoring_app.exe"
#define FlutterReleaseDir "..\app\build\windows\x64\runner\Release"
#define SidecarDistDir "..\backend\dist\auto-scoring-sidecar"

[Setup]
; Never change AppId: it is how Windows recognises an existing install as the
; same product and upgrades it in place instead of installing a second copy.
AppId={{DAAD5D3A-7FB7-402E-B372-3FFFFD789EAE}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
OutputDir=output
OutputBaseFilename=Auto-Scoring-Setup-{#AppVersion}-unsigned
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
; Japanese UI, matching the app itself.
ShowLanguageDialog=no

; Per-user by default, so no administrator prompt is needed and the install
; lands in {localappdata}\Programs\{#AppName} -- the same user profile the
; app's data lives in (docs/windows-distribution.md §3). `dialog` still lets
; someone with admin rights choose a machine-wide install; the app works
; either way because it never writes inside its own install directory.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Flutter Windows and the PyInstaller bundle are both 64-bit only.
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

; Offer to close a running Auto-Scoring rather than failing on locked files or
; silently requiring a reboot. Matters more than usual here: the sidecar holds
; an open handle on its own executable for as long as the app is running.
CloseApplications=yes
RestartApplications=no

; Deliberately no SignTool= directive. Signing is a human-only step performed
; outside CI on an artifact CI produced -- see docs/windows-distribution.md §8.
; Never add a certificate, password, or signing credential to this file.

[Languages]
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Files]
; The Flutter release output: the executable, flutter_windows.dll, the plugin
; DLLs, and data/ (assets + the AOT snapshot).
Source: "{#FlutterReleaseDir}\*"; DestDir: "{app}"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

; The PyInstaller onedir tree, into the `sidecar\` subdirectory the app looks
; in (`app/lib/core/sidecar_paths.dart`'s `sidecarBundleDirectory`). Copied
; straight from `backend/dist/` rather than through a staging directory --
; Inno Setup reads from as many source trees as it likes.
Source: "{#SidecarDistDir}\*"; DestDir: "{app}\sidecar"; \
    Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "デスクトップにショートカットを作成する"; \
    GroupDescription: "追加のショートカット:"; Flags: unchecked

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{#AppName} を起動する"; \
    Flags: nowait postinstall skipifsilent

[Code]
// Uninstall keeps the user's data by default and asks before removing it.
//
// Keeping it is the default because that directory holds the only copy of
// scanned answer PDFs, grades and review history (§23/§27) -- an uninstall
// (including the one an in-place upgrade performs) must not be able to
// destroy a term's marking. Asking at all is because that same data is
// personal information about students (§26): someone decommissioning a
// machine needs a supported way to remove it, not a folder path to find by
// hand. Silent uninstalls keep the data, since nobody is there to answer.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
var
  DataDir: String;
begin
  if CurUninstallStep <> usPostUninstall then
    exit;

  // Must match `auto_scoring.api.sidecar.default_app_data_dir`.
  DataDir := ExpandConstant('{localappdata}') + '\{#AppName}';
  if not DirExists(DataDir) then
    exit;

  if UninstallSilent then
    exit;

  if MsgBox(
       '答案PDF・採点結果・ログを削除しますか?' + #13#10#13#10 +
       DataDir + #13#10#13#10 +
       '「いいえ」を選ぶとデータは残り、再インストール後もそのまま使えます。',
       mbConfirmation, MB_YESNO or MB_DEFBUTTON2) = IDYES then
    DelTree(DataDir, True, True, True);
end;
