# NPU Video Upscaler — experimental alpha

## v0.2.0a9（フレーム処理中の詳細進捗）

- 1フレームの完了を待たず、実際に処理したタイル数から進捗を更新します。全体の割合を小数3桁で表示し、0%のまま動いていないように見える問題を改善しました。
- 処理段階とは別の欄に、完了/推定全フレーム数、現在のフレーム内のタイル数、経過時間、残り時間の目安を常時表示します。
- 残り時間は1フレーム完了後に計算します。出力確定後だけ100%を表示し、失敗・キャンセル時は到達した進捗を保持します。
- NPU専用推論・60秒プレビュー・音声コピー・原本保護を維持します。Windows CIの模擬NPU検証と、実機の表示・長時間変換の検証は別です。

## v0.2.0a8（名目CFR動画の解析・時刻補正）

- 平均FPSと名目FPSの微小な差（相対0.001%以下）を許容し、該当動画の「動画情報解析」失敗を修正。大きな不一致や不正FPSは引き続き拒否します。
- 読み込み時に映像の時刻を名目FPSへ整えてからNPUへ渡します。必要に応じてフレームを間引き・複製し、出力の正確な有理数FPSと音声コピーを維持します。可変時刻の保存は保証しません。
- 元動画の解析と先頭60秒分のFFmpeg読み込み、回帰テストで検証。60秒の1080p映像を実機NPUで最後まで変換した結果は別途確認が必要です。

This prerelease is an **early Windows 11 x64 test build**, *not a validated finished upscaler*.

- Windows per-user installer: `NpuVideoUpscaler-Setup-v*-win-x64.exe`.
- Portable ZIP: `NpuVideoUpscaler-v*-win-x64-portable.zip`.
- SHA-256 sums: `SHA256SUMS.txt`.
- On launch, the app can check GitHub Releases for new versions and safely download a verified installer with your approval.

**Important prerequisites:** use the app's consent-based publisher-direct FFmpeg setup and select a compatible **static-shape OpenVINO super-resolution model**. The installer **does not bundle an AI model**, Intel NPU driver or FFmpeg. Conversion on Core Ultra 5 125H has **not been hardware validated**. This build is **unsigned** and may trigger a Windows SmartScreen warning.

For requirements and limitations, see the [README](https://github.com/hglasswater-boop/npu-video-upscaler#readme), [model validation issue #3](https://github.com/hglasswater-boop/npu-video-upscaler/issues/3), and [release/update design](https://github.com/hglasswater-boop/npu-video-upscaler/blob/main/docs/releases-and-updates.md).

Do not rely on this build to preserve HDR, VFR timestamps, subtitles, non-MP4-compatible audio or arbitrary model inputs.

## v0.2.0a2 change

- Adds optional **First 60 seconds** NPU quality-test export with a distinct filename.
- Source audio is limited to the same 60-second window; short videos remain short.
- Full export remains available. Pretrained NPU-compatible model still not bundled.

## v0.2.0a3 (experimental model setup)

- New model setup controls: install a trusted local BSRGANx2 model ZIP or download a separately published checksum-verified model from the same GitHub Release, with explicit opt-in.
- Setup fails closed if the model cannot compile on **NPU**; no silent CPU/GPU fallback. Cached validated model is auto-selected at next start.
- Experimental BSRGANx2-OpenVINO-INT8.zip is a separate asset with its own SHA-256 digest, source provenance and Apache-2.0 license notice.
- Core Ultra 5 125H NPU compilation, inference speed, and output quality remain **not physically verified**. This is NOT a production release.


## v0.2.0a4 (publisher-direct FFmpeg bootstrap)

- After installer launch or first portable start, opt in to download and verify FFmpeg 9.0.2 Essentials directly from GyanD's fixed GitHub Release. The app caches the two validated tools in per-user LocalAppData and no longer requires system PATH setup.
- **FFmpeg binaries are NOT inside our installer/portable assets.** They are GPLv3 software with `libx264`, retrieved only from the upstream publisher after user consent. See https://ffmpeg.org/legal.html and docs/bundled-media-tools.md for exact pinned ZIP and SHA-256.
- An Intel NPU driver help button opens Intel's official support site. No driver is bundled or silently installed.
- The AI BSRGAN model remains a separate, opt-in project GitHub Release asset. Core Ultra 5 125H NPU inference and real old→new hardware updates still require validation.


## v0.2.0a5（WindowsのFFmpeg設定修正・日本語UI）

- Windows環境でFFmpegセットアップの最後に発生する `[WinError 5] アクセスが拒否されました` を対策。実行ファイルを一時フォルダーで起動せず、最終インストール先への移動後に起動検証します。
- Windowsの一時的なフォルダーロックには限定回数の再試行を実施し、検証完了まで不完全なセットアップ結果を有効扱いしません。以前の失敗で残った不完全なキャッシュも再試行時に復旧を試みます。
- アプリの主要UI、FFmpeg・AIモデル・更新に関する確認画面、エラー表示を日本語化しました。インストーラの表示言語も日本語に対応しました。
- v0.2.0a4→v0.2.0a5はアプリの更新確認からアップデートできます。Windows 11の実機更新・Core Ultra 5 125HのNPU推論は引き続き検証が必要です。

## v0.2.0a6（0%失敗の診断・ffprobe文字コード修正）

- WindowsのCP932環境でUTF-8のffprobe出力が読み取りスレッドを停止させ、JSON解析へNoneを渡す障害を実データで再現し修正しました。出力をバイト列で取得し、呼び出し元でUTF-8として解析します。
- 不正・空・取得不能な動画情報を拒否し、タイムアウト・終了コード・stderrを診断に保持します。
- 処理段階と例外連鎖のスタックトレースを `%LOCALAPPDATA%/NpuVideoUpscaler/Logs` に保存します。入力・モデル・出力のパスをマスクし、映像・音声・JSON全文は記録しません。
- 日本語の段階表示と短い失敗通知からログ保存先を確認できます。
- 引き継ぎ仕様に合わせ、先頭60秒プレビューを初期選択にしました。全編出力はチェックを外して選べます。
- 報告動画は文字コード修正後、既存のCFR検査で拒否されました。当該動画の変換成功、実機NPU推論・画質、実機の更新GUI操作は別途検証が必要です。CPU/GPU自動フォールバックはありません。
# v0.2.0a7: 動画のドラッグ＆ドロップ

MP4/MKV動画を1本、アプリ画面へドラッグ＆ドロップして選べます。先頭60秒プレビューの保存先候補も入ります。手動の保存先は保持し、変換はボタンで開始します。複数ファイルやフォルダー、変換中の入力差し替えは受け付けません。

Qtイベント・日本語/UNCパス・不正なドロップを回帰テストし、Windows CIで検証します。Explorerから配布版への実際のドロップ操作は実機未検証です。NPU専用推論、音声保持、FFmpegセットアップと自動更新の仕様を維持しています。
