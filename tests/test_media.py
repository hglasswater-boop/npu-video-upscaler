from fractions import Fraction

import pytest

from npu_upscaler.media import MediaError, parse_probe, decoder_command, encoder_command


def probe(fps="30000/1001", avg=None, codec="aac", pix_fmt="yuv420p"):
    return {"streams": [
        {"codec_type": "video", "width": 33, "height": 17,
         "pix_fmt": pix_fmt, "r_frame_rate": fps,
         "avg_frame_rate": avg or fps, "nb_frames": "120"},
        {"codec_type": "audio", "codec_name": codec},
    ], "format": {"duration": "4.004"}}


def test_probe_fractional_fps_and_audio():
    info = parse_probe(probe())
    assert info.fps == Fraction(30000, 1001)
    assert (info.width, info.height, info.audio_streams) == (33, 17, 1)
    assert info.total_frames == 120


def test_probe_missing_frame_count_is_estimated():
    data = probe()
    data["streams"][0].pop("nb_frames")
    assert parse_probe(data).total_frames == 120


@pytest.mark.parametrize("data", [
    probe(fps="0/0"),
    probe(fps="24/1", avg="25/1"),
    probe(codec="vorbis"),
    probe(pix_fmt="yuv420p10le"),
    {"streams": []},
])
def test_probe_rejects_unsupported(data):
    with pytest.raises(MediaError):
        parse_probe(data)


def test_commands_use_rational_fps_and_stream_copy():
    info = parse_probe(probe())
    dec = decoder_command("input file.mkv")
    enc = encoder_command("input file.mkv", "temporary.mp4", info, 4)
    assert dec[-1] == "pipe:1"
    assert dec[dec.index("-fps_mode") + 1] == "passthrough"
    assert "-vsync" not in dec
    assert ["-framerate", "30000/1001"] == enc[enc.index("-framerate"):enc.index("-framerate") + 2]
    assert ["-video_size", "132x68"] == enc[enc.index("-video_size"):enc.index("-video_size") + 2]
    assert enc[enc.index("-map") + 1] == "0:v:0"
    assert "1:a?" in enc
    assert enc[enc.index("-c:a") + 1] == "copy"
    assert enc[enc.index("-c:v") + 1] == "libx264"
    assert "-shortest" not in enc


def test_probes_rotation_metadata():
    data = probe()
    data["streams"][0]["tags"] = {"rotate": "90"}
    with pytest.raises(MediaError):
        parse_probe(data)
