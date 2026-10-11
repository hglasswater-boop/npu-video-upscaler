# Codex 引き継ぎノート — NPU Video Upscaler

## 2026-10-11 更新（以下のa5時点の本文より優先）

公開済み最新版はa9。#15はa6のUTF-8 ffprobe読み取り修正と段階別診断で解決、
続く微小なFPS差による解析拒否はa8で修正。a7はドロップ、a9はタイル単位の進捗。
#8は実機a8→a9のGUI更新・設定保持で確認済み。#3は未完了。
Core Ultra 5 125H、OpenVINO2026.4.1、NPUドライバー32.0.100.4724で実NPU推論と
短い合成動画の音声保持は確認済み。1080p60秒完走・主観画質・音声同期・電力は未検証。
利用者は今後のアプリ更新/インストール操作を承認済みで、a9変換を停止して速度改善を
優先することも承認済み。軽量モデルには切り替えず現在のBSRGANの画質を優先する。
perf/npu-throughputでa10を検証中。仕様と実測は[npu-throughput.md](npu-throughput.md)。
公開・インストール済み扱いにする前に現行CI・Release・実機状態を再確認する。

> 状態スナップショット: 2026-10-11。作業開始時には main、Issues、PR、Releases、CIを必ず再取得すること。  
> リポジトリ: https://github.com/hglasswater-boop/npu-video-upscaler  
> Codexの永続ガイド: [../AGENTS.md](../AGENTS.md)

## 1. 現在の到達点

- GitHubのデフォルトブランチ: `main`。GitHub Releases の最新の**公開済み**実験版は **`v0.2.0a5`**（確認日 2026-10-11）。
- アプリは Windows 11 x64 / PySide6 / OpenVINO / NumPy / FFmpeg を使用したNPU専用動画アップスケーラー。
- 入口は日本語のコンパクトな3段階GUI（`npu_upscaler/gui_layout.py`）。「①動画を選ぶ → ②初回準備 → ③変換する」。先頭60秒プレビューが初期選択で、元動画は変更しない。
- Python 3.12、PyInstaller onedir、Inno Setup により per-user の Windows インストーラ、portable ZIP を生成。新バージョンの main ビルド成功時にGitHub実験版Releaseを作成。
- インストーラはPython・OpenVINO・PySide6ランタイムを含む。FFmpeg/ffprobe は **ユーザーの同意を得た後、GyanDのバージョン固定GitHub Releaseから直接取得**。ダウンロードのサイズとSHA-256を検証し、`%LOCALAPPDATA%/NpuVideoUpscaler/MediaTools` のユーザーキャッシュに配置。PATH変更は不要。第三者のGPLv3 FFmpeg実行ファイルを当プロジェクトの配布物に同梱しないこと。
- 試験用BSRGANx2 OpenVINO INT8モデルはGitHub Releaseの**別ZIP資産**。SHA-256検証後、**NPUでコンパイル成功した場合のみ**有効化。
- インストール済みアプリはGitHub Releasesの新版を確認し、利用者の同意を得てインストーラをダウンロード・ハッシュ検証・起動する。変換中は更新を保留。
- 許容動画は SDR/8-bit/名目CFR の MP4/MKV。入力の適合条件外（HDR/VFR/一部音声・字幕等）は明確に拒否する。出力は H.264 MP4、可能な音声はstream copy。テンポラリ出力を成功時だけ置換。
- **物理的な Core Ultra 5 125H でのNPU実推論・モデル互換性・画質・処理速度は未確認**。Windows Actions のCPU/mock/インストーラテスト合格を物理NPU検証と混同しないこと。

## 2. 今すぐ最優先: 60秒プレビューが0%で失敗

**Issue:** https://github.com/hglasswater-boop/npu-video-upscaler/issues/15  
**準備済み作業ブランチ:** `fix/preview-ffprobe-json-diagnostics` （実装前にmainとの差分を再確認）  
**ユーザーの実機症状:** v0.2.0a5の日本語GUI、先頭60秒のプレビューを開始したところ進捗0%で以下の例外文が表示された。

```
失敗: the JSON object must be str, bytes or bytearray, not NoneType
```

**断定できていない点:** どの `json.loads` が例外を出したかはログがないため不明。可能性があるのは `npu_upscaler/media.py::probe_video` の `json.loads(output.stdout)`、OpenVINO内部の処理、その他依存ライブラリ等。通常の `subprocess.run(capture_output=True, text=True)` は標準出力がstrになるため、**ffprobeが原因と決め打ちしないこと**。元ファイルの破損も証拠なし。

### Codexの作業手順 (資料→失敗テスト→最小修正)

1. `npu_upscaler/pipeline.py::run_video` の実行段階を明確にする: パス検証 → FFmpegパス取得 → `probe_video` → `load_npu_model`（実機NPU）→ デコード／フレーム処理／エンコード／出力確定。
2. `probe_video` で `stdout=None`、空文字、非JSON文字列、`null`、JSONがobject以外、ffprobe終了コード異常、OSエラー、タイムアウト、stderrを再現する回帰テストを**先に**追加。意味のある日本語 `MediaError` に統一し、不正動画を受理しない。
3. プレビュー0%エラーの発生段階と例外連鎖・トレースバックを保持して、`%LOCALAPPDATA%/NpuVideoUpscaler/Logs` に**安全な診断ログ**を書き込む仕組みを追加。ログには生の映像・音声フレーム、ユーザーのファイル内容、シークレットを記録しない。パスは必要に応じてマスク/最小化する。
4. GUIの小さな進捗エリアへ生のPythonエラーを無条件に流さない。「動画情報を確認しています」「NPUモデルを読み込んでいます」など段階を示し、失敗時には短い日本語メッセージとログの保存先を知らせる。詳細はログに残す。
5. 例外がffprobe以外のOpenVINO内部なら実機ログを採取できるようにし、`compile_model(model, "NPU")` のまま原因を究明。CPU/GPUへの無断切替禁止。
6. FFmpegを使った1分プレビュー、音声コピー、終了処理、キャンセル、元ファイル保護、GUI日本語表示と更新機能が回帰しないか確認。
7. `python -m pytest -q` → Windows GitHub Actions unit/gui/FFmpeg統合/installer tests → PR → 成功後にマージ。新しい不可変バージョン（通常は `v0.2.0a6`、作業時に最新バージョンを再確認）で新リリースを作る。ユーザーPCでの再実行成功は**ユーザーが確認するまで未検証**と明記。

**調査時の注意:** 開発用の単純なmockが返す `CompletedProcess(stdout=None)` は実環境の原因を証明しない。エラーを覆い隠すだけの `json.loads(output.stdout or '{}')` のようなフォールバックは禁止。曖昧な例外をエラーの段階と内容が分かる検証例外に置き換えること。

## 3. 次の優先順位

### P1 — 物理 Intel Core Ultra 5 125H のNPU検証
Issue: https://github.com/hglasswater-boop/npu-video-upscaler/issues/3

- 正規のNPUドライバーと `ov.Core().available_devices` の `NPU` 表示を確認。
- 配布済みBSRGANx2静的INT8 IRの実機コンパイル、最初の1タイル推論、実際の60秒動画処理を順に確認。
- 入出力形状/正規化を確認し、シーム・画質劣化・処理速度・音声同期を計測する。GitHub CIは代替にならない。
- モデルコンパイル失敗時は該当ドライバー/OpenVINOバージョンとスタックトレースを保存し、NPU専用要件を保持。

### P2 — 実際のアップデーター操作検証
Issue: https://github.com/hglasswater-boop/npu-video-upscaler/issues/8

- Windowsランナーでは**実際の旧版→新版のインストーラ更新**とハッシュ/設定維持チェックが実装・成功した履歴があるが、利用者がGUIから更新を承認して起動する実機シナリオは未検証。
- 初回起動の日本語ダイアログと自動更新が競合しないこと、処理中の更新保留、アプリ設定維持、インストーラ終了後の新版起動まで確認。

### P3 — 利用者体験の継続改善
- 3段階の日本語GUI、横幅上限840px、重要な技術設定は「詳細設定」内、60秒プレビュー初期選択を維持。
- 画面上の現在の状態（動画未選択・FFmpeg/モデル未設定・NPUドライバー・処理中）に応じて次にすべき操作を1つに絞って明示。準備済みなら操作を減らす。
- 旧ドキュメントのFFmpeg-on-PATHなど古い記述を現行実装に合わせる。
- Issue #11 は元の「FFmpegを同梱」の仕様が残っているが、**現行設計はライセンスへの配慮により配布元からの直接ダウンロード方式**。古いIssueの記述だけを根拠に再同梱しないこと。

## 4. 重要なファイル/仕様

| 場所 | 用途 |
| --- | --- |
| `AGENTS.md` | Codexが毎回読む永続指示 |
| `npu_upscaler/gui.py` | PySide6操作、非同期worker、更新・ダウンロード・エラー表示 |
| `npu_upscaler/gui_layout.py` | 横長にしない日本語3段階レイアウト |
| `npu_upscaler/media.py` | ffprobe JSON、入力映像検証、FFmpegコマンド作成 |
| `npu_upscaler/pipeline.py` | 60秒フレーム上限、NPU変換、音声、キャンセル、テンポラリ出力 |
| `npu_upscaler/npu.py` | OpenVINO NPU専用コンパイル、タイリング |
| `npu_upscaler/media_tools.py` | GyanD FFmpeg直接ダウンロード、SHA-256、Windowsキャッシュ |
| `npu_upscaler/model_packages.py` / `model_download.py` | モデル配布・検証 |
| `npu_upscaler/updates.py` | 公式GitHub Releases自動更新 |
| `launcher.py` / `installer.iss` | Windows exe / インストーラ |
| `.github/workflows/test.yml` | Windows Python/Qtテスト |
| `.github/workflows/windows-build-release.yml` | Windowsビルド・モデルZIP生成・main Release |
| `docs/architecture.md`, `docs/quick-preview.md`, `docs/model-preparation.md`, `docs/bundled-media-tools.md` | 仕様と検証条件 |
| `docs/releases-and-updates.md` | 更新方針（古い記述もあるため検証して読む） |

## 5. 開発・リリース規約

- 機能追加/修正の前に**Issue/仕様→テスト→修正→不要分削除と整合確認**を基本とする。
- Python **3.12**で `python -m pip install -e ".[dev]"`、`python -m pytest -q`。GUIテストは `QT_QPA_PLATFORM=offscreen` を使用できる。FFmpeg統合テストはFFmpegのある環境で実行。
- FFmpegは GPLv3/GyanDの配布元から利用者が同意して取得する。ZIPのピン留めSHA-256やダウンロード先、パス分離の安全性を保持。配布物に再同梱しない。
- モデルのコンパイル先は**常にNPUのみ**。Windows CIのCPU/mockテストはハードウェアの成功保証ではない。
- ソフトウェア更新は**新しいタグ**でRelease。既存タグ/assetの差し替えは禁止。バージョン文字列は `npu_upscaler/__init__.py` の `__version__` を変更。
- Windowsインストーラとportable ZIP、モデルZIP、SHA256SUMSの資産が揃い、Windows CIが成功したことを公開後に確認する。
- 完了報告では、再現/原因、変更ファイル、テスト結果、PR、Release、**未検証の実機項目**を区別する。

## 6. Codex向け着手指示

1. `main` から最新を取得し、`AGENTS.md` とこの文書、Issue #15を読む。
2. `fix/preview-ffprobe-json-diagnostics` の状態（空・既存コミット）を確認し、競合を避けて作業ブランチを使う。
3. まず「0%のJSON NoneType失敗」の診断機能と回帰テストを実装し、FFmpegとOpenVINOのどこで失敗したか利用者からログを取得できるようにする。
4. テスト→PR→CI→新alphaのリリースを進める。ログが原因を示したら同じIssue内で修正を続ける。
5. その後、Issue #3 の125H実機NPU検証、およびIssue #8の更新UI実機検証を段階的に進める。

**安全上の最重要事項:** 現在の0%例外はスクリーンショットのみで原因未確定。直ったという宣言は、実機ログを解析するか再現テストで原因を実証してから行うこと。
