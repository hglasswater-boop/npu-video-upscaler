# GPU標準への移行 — Issue #23

**目的:** Core Ultra 5 125Hの内蔵Intel Arc GPUにBSRGANx2の超解像推論を移し、NPUは明示的な省電力モードとして残す。以前の「NPU専用」方針は、2026-10-11のユーザー判断で変更された。

## 事実と未確認事項

- `docs/npu-throughput.md` 実機のNPU測定: 同じ1080pフレームを128pxタイルへreshapeすると約35.90秒/フレーム。48pxの約60.79秒より改善したが実用性が十分でない。
- 60秒/約26時間は完走実測ではなく処理速度からの推定。GPUなら何倍速くなるか、速度保証なし。
- OpenVINOのGPUプラグインを`core.compile_model(model,'GPU')`で明示使用。GPUがなければエラーを表示し、CPUやNPUへの暗黙の自動切替はしない。
- 現在の公開BSRGANx2パッケージは48px入力のINT8_ASYM重み圧縮IRで、検証済みキャッシュモデルだけインメモリで128pxへreshapeする。GPUプラグインでこのIRと128px reshapeが実際にコンパイルできるかはユーザー実機で確認する必要がある。FP16 GPU向けIRの作成は後続課題。
- モデル初回セットアップは選択中のアクセラレータで事前コンパイル検証する。既存のモデル・FFmpegキャッシュは共有する。
- ユーザーは軽量モデルに置き換えず既存BSRGANの画質を重視するため、ベンチマークは同じ重み/タイル条件から開始。

## 受け入れ条件 — 第一段階

1. GUIの「AI推論デバイス」は **GPU（高速・Intel Arc）** をデフォルト、NPUは明示選択、選択をQSettingsに保存。変換開始時の選択をworkerのスナップショットとして固定する。
2. GPUを`available_devices`で確認し、該当デバイス専用にコンパイル。GPUが無い/失敗した場合にNPU/CPU/AUTOに代替しない。
3. 別配布の同じBSRGANx2モデルZIPをGPU用に初回設定可能。NPUだけしか利用できない場合もNPUを選べば利用可能。
4. タイル分割8pxオーバーラップ、色・shape検査、音声copy、先頭60秒、取消、出力原子性、更新同意を変更しない。
5. Python/Qtテスト、Windows Actions、FFmpeg統合・インストーラテスト。CIのCPU/mocked GPUは実機GPU検証を意味しない。
6. 最新版がmainに出た後、利用者の125H上で最初は**5秒1080p**を推奨。GPUあり/コンパイル可否、推論実FPS、所要時間、GPU使用率、画質の違い、音声とFPSを記録する。失敗したら`%LOCALAPPDATA%/NpuVideoUpscaler/Logs`の診断を使う。

## 第二段階（ベースライン計測後）

- Intel Arc向けGPU FP16 IR（BSRGANの元重み・出力画質の比較含む）、128/192/256pxのバッチ性能測定、非同期InferRequestの効果を確認。
- Intel Quick Sync H.264ハードウェアエンコードをオプションとして追加、`libx264`と比較。色形式・音声copy・互換性を保つ。
- デコード/色変換/前処理/推論/タイル結合/エンコード/ディスクI/Oを計時して真のボトルネックを数値で特定する。
- GPUとNPUの同時分散は転送/同期コストの測定結果を確認するまで実装しない。

## CIと公開

`python -m pytest -q`とWindows CI両方の成功を条件にPRマージ。GPUハードウェア動作はユーザー実機の短い動画で検証する。バージョンの既存タグを上書きせず、新しいalpha版としてReleaseする。
