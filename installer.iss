#ifndef AppVersion
  #error AppVersion must be passed via ISCC /DAppVersion=x.y.z
#endif

[Setup]
AppId={{4B8E4E7E-2A49-46B3-A2F9-AF9584A31735}
AppName=NPU Video Upscaler
AppVersion={#AppVersion}
AppVerName=NPU Video Upscaler {#AppVersion} (Experimental)
AppPublisher=hglasswater-boop
AppPublisherURL=https://github.com/hglasswater-boop/npu-video-upscaler
DefaultDirName={localappdata}\Programs\NpuVideoUpscaler
DefaultGroupName=NPU Video Upscaler
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
ArchitecturesAllowed=x64
OutputDir=dist\installer
OutputBaseFilename=NpuVideoUpscaler-Setup-v{#AppVersion}-win-x64
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
UninstallDisplayIcon={app}\NpuVideoUpscaler.exe
CloseApplications=yes
RestartApplications=no

[Files]
Source: "dist\NpuVideoUpscaler\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\NPU Video Upscaler"; Filename: "{app}\NpuVideoUpscaler.exe"

[Run]
Filename: "{app}\NpuVideoUpscaler.exe"; Description: "Launch NPU Video Upscaler and set up FFmpeg"; Flags: nowait postinstall skipifsilent
