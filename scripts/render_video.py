#!/usr/bin/env python3
"""Local news-card video builder. Requires Pillow, FFmpeg, and (for real audio) Piper TTS."""
from __future__ import annotations
import argparse
import datetime as dt
import hashlib
import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import wave
from pathlib import Path
from urllib.parse import urlparse

W, H = 1080, 1920
SUPPORTED = {'vi', 'en'}
DEMO_WATERMARK = 'DEMO • KHÔNG PHẢI TIN THẬT'
_PIPER_VOICE_CACHE = {}  # Keep loaded Piper ONNX models between phrase syntheses.


def clean(s: str) -> str:
    return '' if s is None else ' '.join(str(s).split()).strip()


def domain(url: str) -> str:
    parts = urlparse(url)
    if parts.scheme not in ('http', 'https') or not parts.netloc:
        raise ValueError('Nguồn phải có URL http(s) hợp lệ: ' + url)
    return parts.netloc.lower().removeprefix('www.')


def validate_brief(brief: dict, allow_demo: bool = False) -> None:
    if not isinstance(brief, dict):
        raise ValueError('File đầu vào phải là JSON object')
    demo = brief.get('demo') is True
    if demo and not allow_demo:
        raise ValueError('Đây là dữ liệu giả lập. Thêm --allow-demo để thử nghiệm; không được đăng tải.')
    if not demo and brief.get('status') != 'approved':
        raise ValueError('Video thật chỉ dựng khi status=approved')
    if not isinstance(brief.get('stories'), list) or not 1 <= len(brief['stories']) <= 15:
        raise ValueError('Yêu cầu 1–15 tin')
    if type(brief.get('target_seconds')) is not int or not 15 <= brief['target_seconds'] <= 180:
        raise ValueError('target_seconds phải là số nguyên 15–180')
    if clean(brief.get('country', '')) == '' or clean(brief.get('category', '')) == '':
        raise ValueError('Thiếu country/category')
    if brief.get('aspect_ratio', '9:16') not in ('9:16','16:9','both'):
        raise ValueError('aspect_ratio must be 9:16, 16:9 or both')
    language = brief.get('language', '')
    if not isinstance(language, str) or language.split('-')[0] not in SUPPORTED:
        raise ValueError('Bản MVP hỗ trợ viết và đọc vi/en, mở rộng trong phiên bản sau')
    if not clean(brief.get('as_of', '')):
        raise ValueError('Thiếu as_of có múi giờ')
    try:
        t = dt.datetime.fromisoformat(brief['as_of'].replace('Z', '+00:00'))
        if t.tzinfo is None: raise ValueError('as_of phải có múi giờ')
    except Exception as e:
        raise ValueError('as_of không hợp lệ: ' + str(e)) from e
    for index, item in enumerate(brief['stories'], 1):
        prefix = f'Tin {index}: '
        if not isinstance(item, dict):
            raise ValueError(prefix + 'phải là JSON object')
        for field in ('headline', 'narration', 'summary'):
            if not isinstance(item.get(field), str) or not clean(item.get(field, '')):
                raise ValueError(prefix + 'thiếu ' + field)
        if not demo and item.get('approved') is not True:
            raise ValueError(prefix + 'chưa được người dùng duyệt')
        sources = item.get('sources', [])
        if not isinstance(sources, list) or len(sources) < 2:
            raise ValueError(prefix + 'phải có >=2 nguồn độc lập đã kiểm chứng')
        domains = set()
        for src in sources:
            if not isinstance(src, dict) or not isinstance(src.get('url'), str):
                raise ValueError(prefix + 'nguồn phải có URL dạng chuỗi')
            domains.add(domain(src['url']))
            if not clean(src.get('title', '')) or not clean(src.get('published_at', '')):
                raise ValueError(prefix + 'nguồn thiếu tiêu đề / thời điểm')
        if len(domains) < 2:
            raise ValueError(prefix + 'hai URL cùng một miền, không đủ nguồn độc lập')
        picture = item.get('image_path')
        if picture and not isinstance(picture, str):
            raise ValueError(prefix + 'image_path phải là chuỗi')
        if picture and not clean(item.get('image_license', '')):
            raise ValueError(prefix + 'ảnh phải có image_license và quyền sử dụng được kiểm tra')
        if picture and (Path(str(picture)).is_absolute() or '..' in Path(str(picture)).parts):
            raise ValueError(prefix + 'image_path phải là đường dẫn tương đối an toàn')
        if len(item['narration']) > 4000:
            raise ValueError(prefix + 'kịch bản dài quá mức')
    if not demo:
        approval = brief.get('approval_record')
        if not isinstance(approval, dict) or not clean(approval.get('user_confirmation')):
            raise ValueError('Thiếu minh chứng người dùng đã phê duyệt kịch bản')
        draft = json.loads(json.dumps(brief, ensure_ascii=False))
        draft.pop('approval_record', None)
        draft['status'] = 'draft'
        for item in draft['stories']:
            item['approved'] = False
        expected = hashlib.sha256(json.dumps(draft, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode('utf-8')).hexdigest()
        if approval.get('approved_script_sha256') != expected:
            raise ValueError('Kịch bản bị thay đổi sau khi duyệt; yêu cầu phê duyệt lại')


def font_path(bold: bool) -> str:
    paths = [
        Path('C:/Windows/Fonts/arialbd.ttf' if bold else 'C:/Windows/Fonts/arial.ttf'),
        Path('C:/Windows/Fonts/segoeuib.ttf' if bold else 'C:/Windows/Fonts/segoeui.ttf'),
        Path('/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf' if bold else '/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf'),
    ]
    for p in paths:
        if p.is_file(): return str(p)
    raise RuntimeError('Không tìm thấy font Unicode hỗ trợ tiếng Việt')


def font(size: int, bold=False):
    from PIL import ImageFont
    return ImageFont.truetype(font_path(bold), size=size)


def wrap_pixels(draw: ImageDraw.ImageDraw, msg: str, fnt: ImageFont.FreeTypeFont, max_width: int, max_lines: int | None = None) -> list[str]:
    lines = []
    for paragraph in clean(msg).split('\n'):
        words = paragraph.split()
        line = ''
        for word in words:
            if draw.textbbox((0, 0), (line + ' ' + word).strip(), font=fnt)[2] <= max_width:
                line = (line + ' ' + word).strip()
            else:
                if line: lines.append(line)
                line = word
        if line: lines.append(line)
    if max_lines and len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + '…', font=fnt)[2] > max_width:
            lines[-1] = lines[-1][:-1]
        lines[-1] += '…'
    return lines


def make_card(brief: dict, item: dict, number: int, out: Path, base: Path):
    from PIL import Image, ImageDraw, ImageOps
    background = Image.new('RGB', (W, H), (8, 19, 44))
    d = ImageDraw.Draw(background)
    for y in range(H):
        k = y/H
        d.line((0, y, W, y), fill=(int(10+12*k), int(21+10*k), int(48+11*k)))
    # compositional decorations
    d.ellipse((640, -160, 1370, 570), fill=(20, 43, 78))
    d.ellipse((-260, 1300, 420, 1980), fill=(15, 39, 73))
    d.rounded_rectangle((66, 96, 424, 162), radius=25, fill=(221, 48, 62))
    d.text((96, 108), 'TIN TỨC • NEWS', font=font(35, True), fill='white')
    d.text((70, 215), f'{brief["country"].upper()}  /  {brief["category"].upper()}', font=font(39, True), fill=(112, 208, 251))
    d.rounded_rectangle((70, 318, 1010, 1115), radius=30, fill=(28, 48, 78))
    photo = item.get('image_path')
    if photo:
        img_file = (base / photo).resolve()
        if not img_file.is_relative_to(base.resolve()):
            raise ValueError('image_path phai nam trong thu muc du lieu da duyet')
        if not img_file.is_file(): raise ValueError('Không tìm thấy ảnh: ' + str(img_file))
        with Image.open(img_file) as im:
            picture = ImageOps.fit(im.convert('RGB'), (910, 390))
        background.paste(picture, (85, 335))
        d = ImageDraw.Draw(background)
        headline_start = 765
    else:
        d.text((103, 365), f'TIN {number:02d}', font=font(76, True), fill=(112, 208, 251))
        d.line((103, 484, 924, 484), fill=(77, 107, 139), width=4)
        headline_start = 555
    headline = wrap_pixels(d, item['headline'], font(67, True), 818, max_lines=6 if not photo else 4)
    for j, line in enumerate(headline):
        d.text((104, headline_start + j*100), line, font=font(67, True), fill='white')
    d.rounded_rectangle((72, 1210, 1008, 1535), radius=22, fill=(29, 54, 83))
    d.text((103, 1243), 'TÓM TẮT', font=font(36, True), fill=(117, 206, 243))
    summary = wrap_pixels(d, item['summary'], font(40), 832, max_lines=4)
    for j, line in enumerate(summary):
        d.text((103, 1310 + j*53), line, font=font(40), fill=(234, 241, 248))
    d.text((83, 1715), 'NGUỒN TIN ĐÃ ĐỐI CHIẾU', font=font(30, True), fill=(125, 211, 240))
    src = ' • '.join(x['title'][:28] for x in item['sources'][:3])
    for j, line in enumerate(wrap_pixels(d, src, font(30), 900, max_lines=1)):
        d.text((83, 1755 + 42*j), line, font=font(30), fill=(198, 214, 230))
    if brief.get('demo'):
        d.rounded_rectangle((70, 1817, 1010, 1896), radius=15, fill=(139, 27, 40))
        d.text((96, 1833), DEMO_WATERMARK, font=font(35, True), fill='white')
    background.save(out)


def chunks(text: str, max_chars=58) -> list[str]:
    """Keep each caption close to spoken text; audio is generated for each chunk separately."""
    candidates = re.split(r'(?<=[.!?;:。！？])\s+', clean(text))
    out = []
    for sentence in candidates:
        current = ''
        for word in sentence.split():
            test = (current + ' ' + word).strip()
            if len(test) <= max_chars:
                current = test
            else:
                if current: out.append(current)
                current = word
        if current: out.append(current)
    return [s for s in out if s]


def stamp(seconds: float) -> str:
    ms = int(round(max(0, seconds)*1000))
    h, rest = divmod(ms, 3600000)
    m, rest = divmod(rest, 60000)
    s, ms = divmod(rest, 1000)
    return f'{h:02d}:{m:02d}:{s:02d},{ms:03d}'


def write_srt(items: list[tuple[float, float, str]], dst: Path):
    blocks = []
    for i, (start, end, txt) in enumerate(items, 1):
        blocks.append(f'{i}\n{stamp(start)} --> {stamp(end)}\n{txt}\n')
    dst.write_text('\n'.join(blocks), encoding='utf-8-sig')


def synth_piper(text: str, outfile: Path, voice: str):
    model_dir = Path(os.environ.get('PIPER_VOICE_DIR', str(Path(__file__).resolve().parents[1] / 'models')))
    args = [sys.executable, '-m', 'piper', '-m', voice, '--data-dir', str(model_dir), '-f', str(outfile)]
    speed = float(os.environ.get('PIPER_SPEECH_RATE', '1.0'))
    if not 0.75 <= speed <= 1.35:
        raise ValueError('Piper speech rate must be between 0.75 and 1.35')
    args += ['--length-scale', str(round(1.0 / speed, 4))]
    lexicon = os.environ.get('PIPER_PRONUNCIATION_MAP')
    if lexicon:
        substitutions = json.loads(Path(lexicon).read_text(encoding='utf-8-sig'))
        if not isinstance(substitutions, dict) or len(substitutions) > 150 or any(not isinstance(k,str) or not isinstance(v,str) or not k or len(v)>160 for k,v in substitutions.items()):
            raise ValueError('Invalid pronunciation substitution lexicon')
        for written, spoken in sorted(substitutions.items(), key=lambda x:len(x[0]), reverse=True):
            text = re.sub(r'(?<!\w)' + re.escape(written) + r'(?!\w)',lambda m:spoken,text)
    if os.environ.get('PIPER_BACKEND', 'inprocess') == 'inprocess':
        from piper import PiperVoice, SynthesisConfig
        model = (model_dir / (voice + '.onnx')).resolve()
        if not model.is_file() or not (model_dir / (voice + '.onnx.json')).is_file():
            raise ValueError('Missing local Piper model/config: ' + str(model))
        key = str(model)
        if key not in _PIPER_VOICE_CACHE:
            _PIPER_VOICE_CACHE[key] = PiperVoice.load(model)
        with wave.open(str(outfile), 'wb') as target:
            _PIPER_VOICE_CACHE[key].synthesize_wav(text, target,
                SynthesisConfig(length_scale=round(1.0 / speed, 4)))
        return
    piper_env = dict(os.environ, PYTHONIOENCODING='utf-8')
    proc = subprocess.run(args, input=text + '\n', capture_output=True, text=True, encoding='utf-8', env=piper_env, timeout=240)
    if proc.returncode != 0 or not outfile.exists():
        raise RuntimeError('Piper TTS lỗi: ' + (proc.stderr or proc.stdout)[-800:] + '\nĐã cài pip install piper-tts và tải model giọng chưa?')


def silence_wav(dst: Path, length: float, params=None):
    rate, channels, width = params or (22050, 1, 2)
    with wave.open(str(dst), 'wb') as f:
        f.setnchannels(channels); f.setsampwidth(width); f.setframerate(rate)
        f.writeframes(b'\x00'*int(rate*length)*channels*width)


def build_audio(parts: list[str], work: Path, prefix: str, voice: str, demo_silence: bool):
    block_paths = []
    durations = []
    for i, phrase in enumerate(parts):
        p = work/f'{prefix}_voice_{i:03d}.wav'
        if demo_silence:
            silence_wav(p, max(1.8, len(phrase)/12.5))
        else:
            synth_piper(phrase, p, voice)
        with wave.open(str(p), 'rb') as f:
            durations.append(f.getnframes()/f.getframerate())
        block_paths.append(p)
    output = work/f'{prefix}_voice.wav'
    subtitles = []
    cursor = 0.22
    with wave.open(str(output), 'wb') as dest:
        reference = None
        for i, (p, dur, phrase) in enumerate(zip(block_paths, durations, parts)):
            with wave.open(str(p), 'rb') as src:
                fmt = (src.getframerate(), src.getnchannels(), src.getsampwidth())
                if reference is None:
                    reference = fmt
                    dest.setframerate(fmt[0]); dest.setnchannels(fmt[1]); dest.setsampwidth(fmt[2])
                    dest.writeframes(b'\0' * round(fmt[0]*0.22)*fmt[1]*fmt[2])
                elif reference != fmt:
                    raise RuntimeError('Piper tạo WAV không nhất quán giữa các câu.')
                dest.writeframes(src.readframes(src.getnframes()))
            subtitles.append((cursor, cursor+dur, phrase))
            cursor += dur
            # Respect audible sentence boundaries rather than inserting an
            # identical robotic pause after every TTS chunk.
            if phrase.rstrip().endswith(('.', '!', '?', '。', '！', '？')):
                pause = .29
            elif phrase.rstrip().endswith((',', ';', ':', '，', '；')):
                pause = .17
            else:
                pause = .13
            if i == len(parts) - 1:
                pause = .07
            dest.writeframes(b'\0' * round(reference[0]*pause)*reference[1]*reference[2])
            cursor += pause
    return output, subtitles, cursor


def run(cmd, cwd: Path | None=None):
    p = subprocess.run(cmd, cwd=str(cwd) if cwd else None, capture_output=True, text=True)
    if p.returncode:
        raise RuntimeError('Lệnh thất bại: ' + ' '.join(map(str, cmd)) + '\n' + p.stderr[-1500:])
    return p.stdout


def media_duration(path: Path) -> float:
    p = run(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', str(path)])
    return float(p.strip())


def verify_media(path: Path) -> dict:
    info = json.loads(run(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(path)]))
    streams = info.get('streams', [])
    videos = [x for x in streams if x.get('codec_type') == 'video']
    audios = [x for x in streams if x.get('codec_type') == 'audio']
    if len(videos) != 1 or not audios:
        raise RuntimeError('QA: video phải có một luồng hình và ít nhất một luồng âm thanh')
    v, a = videos[0], audios[0]
    if (v.get('width'), v.get('height')) != (W, H) or v.get('codec_name') != 'h264' or a.get('codec_name') != 'aac':
        raise RuntimeError('QA: sai độ phân giải 1080x1920 hoặc codec H.264/AAC')
    return {'width': v['width'], 'height': v['height'], 'video_codec': v['codec_name'],
            'audio_codec': a['codec_name'], 'audio_sample_rate': a.get('sample_rate')}


def nvenc_available() -> bool:
    try:
        run(['ffmpeg', '-hide_banner', '-loglevel', 'error', '-f', 'lavfi',
             '-i', 'color=c=black:s=64x64:d=0.1', '-frames:v', '1',
             '-c:v', 'h264_nvenc', '-f', 'null', '-'])
        return True
    except (RuntimeError, OSError):
        return False


def ffmpeg_render(work: Path, i: int, duration: float, encoder: str = 'libx264'):
    stem = f'story_{i:02d}'
    clip = work/(stem+'.mp4')
    vf = "subtitles=" + stem + ".srt:force_style='FontSize=10,Bold=1,Alignment=2,Outline=1,Shadow=0,MarginV=32'"
    enc_args = (['-c:v', 'h264_nvenc', '-preset', 'p4', '-cq', '23'] if encoder == 'h264_nvenc'
                else ['-c:v', 'libx264', '-preset', 'veryfast', '-crf', '23'])
    cmd = ['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-loop', '1', '-framerate', '30', '-i', stem+'.png', '-i', stem+'_voice.wav',
           '-t', f'{duration:.3f}', '-vf', vf, '-r', '30'] + enc_args + ['-pix_fmt', 'yuv420p',
           '-c:a', 'aac', '-b:a', '160k', '-af', 'apad', '-movflags', '+faststart', stem+'.mp4']
    run(cmd, cwd=work)
    return clip


def duration_status(seconds: float, target: int, allow_longer: bool = False) -> str:
    if seconds <= target + 5:
        return 'PASS'
    return 'PASS_LONGER_ACCEPTED' if allow_longer else 'NEEDS_EDITORIAL_TRIM'


def main():
    ap = argparse.ArgumentParser(description='Tạo bản tin video dọc bằng Piper+FFmpeg, phụ đề cháy và SRT ngoài')
    ap.add_argument('--input', type=Path, required=True)
    ap.add_argument('--out', type=Path, required=True)
    ap.add_argument('--voice', default='vi_VN-vais1000-medium')
    ap.add_argument('--allow-demo', action='store_true')
    ap.add_argument('--encoder', choices=['auto', 'cpu', 'nvenc'], default='auto', help='auto chọn NVENC nếu kiểm thử thành công, ngược lại x264 CPU')
    ap.add_argument('--demo-silence', action='store_true', help='Chỉ dùng kiểm thử DEMO, không tạo giọng thật')
    ap.add_argument('--dry-run', action='store_true', help='Kiểm tra dữ liệu, không dựng video')
    ap.add_argument('--allow-longer', action='store_true', help='Cho phép vượt target_seconds, ghi rõ cảnh báo trong QA')
    args = ap.parse_args()
    brief_file = args.input.resolve()
    brief = json.loads(brief_file.read_text(encoding='utf-8-sig'))
    validate_brief(brief, args.allow_demo)
    if brief.get('aspect_ratio','9:16') != '9:16':
        raise ValueError('Legacy renderer only supports 9:16; use video_pipeline.py for 16:9/both')
    if args.demo_silence and not brief.get('demo'):
        raise ValueError('--demo-silence chỉ được dùng với dữ liệu DEMO')
    if args.dry_run:
        print(json.dumps({'valid': True, 'stories': len(brief['stories']), 'demo': bool(brief.get('demo')), 'target_seconds': brief['target_seconds']}, ensure_ascii=False, indent=2))
        return
    if not shutil.which('ffmpeg') or not shutil.which('ffprobe'):
        raise RuntimeError('Thiếu FFmpeg/ffprobe trên PATH')
    available_gpu = nvenc_available() if args.encoder != 'cpu' else False
    if args.encoder == 'nvenc' and not available_gpu:
        raise RuntimeError('NVENC được yêu cầu nhưng FFmpeg/driver/GPU không hỗ trợ')
    selected_encoder = 'h264_nvenc' if available_gpu else 'libx264'
    root = args.out.resolve()
    if root.exists() and any(root.iterdir()):
        raise ValueError('Thư mục output không trống; chọn thư mục khác để tránh ghi đè: ' + str(root))
    root.mkdir(parents=True, exist_ok=True)
    work = root/'_work'
    work.mkdir()
    clips=[]; all_subs=[]; cursor=0.0
    for i, item in enumerate(brief['stories'], 1):
        stem = f'story_{i:02d}'
        make_card(brief, item, i, work/(stem+'.png'), brief_file.parent)
        parts = chunks(item['narration'])
        voice_path, subs, duration = build_audio(parts, work, stem, args.voice, args.demo_silence)
        write_srt(subs, work/(stem+'.srt'))
        clips.append(ffmpeg_render(work, i, duration, selected_encoder))
        all_subs.extend((a+cursor, b+cursor, t) for a,b,t in subs)
        cursor += media_duration(clips[-1])
    playlist = work/'clips.txt'
    playlist.write_text(''.join("file '" + p.name + "'\n" for p in clips), encoding='utf-8')
    final = root/('DEMO_DO_NOT_PUBLISH.mp4' if brief.get('demo') else 'news_video_9x16.mp4')
    run(['ffmpeg', '-y', '-hide_banner', '-loglevel', 'error', '-f', 'concat', '-safe', '0', '-i', 'clips.txt', '-c', 'copy', str(final)], cwd=work)
    write_srt(all_subs, root/'subtitles.srt')
    elapsed = media_duration(final)
    media_info = verify_media(final)
    over_target = elapsed > brief['target_seconds'] + 5
    status = duration_status(elapsed, brief['target_seconds'], args.allow_longer)
    report = {
        'status': status, 'video': final.name, 'duration_seconds': round(elapsed, 2),
        'target_seconds': brief['target_seconds'], 'resolution': '1080x1920',
        'technical_media_checks': media_info,
        'video_encoder': selected_encoder,
        'audio': 'SILENCE_TEST_ONLY' if args.demo_silence else 'PIPER_TTS',
        'subtitle': 'burned_and_separate_SRT', 'demo': bool(brief.get('demo')),
        'source_manifest': str(brief_file), 'stories': len(brief['stories']),
        'editorial_review_required': True,
        'over_target': over_target,
        'disclaimer': 'DEMO không được xuất bản' if brief.get('demo') else 'Cần nghe, xem, kiểm nguồn và quyền media trước khi đăng',
    }
    (root/'qa_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    (root/'sources.json').write_text(json.dumps([{'headline':x['headline'],'sources':x['sources']} for x in brief['stories']], ensure_ascii=False, indent=2), encoding='utf-8')
    metadata = {'title': clean(brief.get('video_title') or (brief['country']+' | '+brief['category']+' | Bản tin')),
                'description': clean(brief.get('video_description') or 'Tổng hợp và bình luận từ các nguồn được dẫn trong sources.json. Nội dung được AI hỗ trợ biên tập.'),
                'hashtags': brief.get('hashtags', ['#tintuc', '#news', '#shorts'])}
    (root/'publishing_metadata.json').write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if status == 'NEEDS_EDITORIAL_TRIM':
        raise SystemExit('CẦN BIÊN TẬP LẠI: video vượt thời lượng đặt ra. Không được coi là sẵn sàng xuất bản.')


if __name__ == '__main__':
    try: main()
    except (ValueError, RuntimeError, OSError, KeyError, json.JSONDecodeError) as e:
        print('ERROR:', e, file=sys.stderr)
        sys.exit(2)
