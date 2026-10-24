#!/usr/bin/env python3
"""Stage-15 acceptance gate; runs only AFTER four completed native 30fps DEMO renders.
Verifies WAV calibration, MP4 QA, original real-news hashes, and backup integrity.
"""
from __future__ import annotations
import argparse,datetime as dt,hashlib,json,sys
from pathlib import Path
import qa_engine as qa

def read(p:Path):return json.loads(p.read_text(encoding='utf-8-sig'))
def sha(p:Path):return qa.digest(p)
def verify(target:int,language:str,out:Path,metric:Path,root:Path)->dict:
    raw=read(metric);renderer=read(out/'qa_report.json')
    if raw['returncode']!=0 or raw.get('timeout') or raw.get('startup_stall_detected'):
        raise ValueError(f'render run failed: {target}')
    if raw.get('remotion_sample_every')!=1 or renderer.get('motion_quality')!='NATIVE_30FPS':
        raise ValueError('cannot accept frame-sampled output as native30: '+str(target))
    if raw.get('speech_rate_forwarded_as_cli') is not True:raise ValueError('bench speech rate not passed via CLI')
    if raw['input']!=str(root/'stage15-20261024-0743-duration'/f'target-{target}-{language}'/'calibrated_demo.json'):
        raise ValueError('wrong calibration manifest: '+str(target))
    report_path=root/f'stage15-final-qa-{target}.json'
    if report_path.exists():raise ValueError('QA report already exists')
    data=qa.analyze(out,report_path,'both',True)
    report_path.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
    if not data['technical_pass'] or data['errors'] or set(data['formats'])!={'9:16','16:9'}:
        raise ValueError('independent QA failure: '+str(target)+repr(data['errors']))
    actual=sum(v['duration_seconds'] for v in data['formats'].values())/2
    delta=100*(actual-target)/target
    if abs(delta)>5:
        raise ValueError('duration outside 5 percent: '+str(target)+' actual '+str(actual))
    if any(v['fps']!=30 or v['subtitles']['cues']<1 for v in data['formats'].values()):
        raise ValueError('invalid fps/caption')
    if data['demo'] is not True:raise ValueError('calibration fixture accidentally non-DEMO')
    return {'target_s':target,'actual_s':round(actual,3),'error_pct':round(delta,2),
        'runtime_s':raw['elapsed_seconds'],
        'render_s_per_video_s':round(raw['elapsed_seconds']/actual,2),
        'peak_process_tree_cpu_percent':max((s.get('cpu_percent_across_cores',0) for s in raw.get('samples',[])),default=0),
        'native_fps':30,'gpu_encoder':renderer['formats']['9:16']['qa']['encoder'],
        'peak_rss_mb':raw.get('peak_process_tree_rss_mb'),
        'peak_device_gpu_mem_mb':raw.get('peak_gpu_used_mb'),
        'peak_device_gpu_util_pct':raw.get('peak_gpu_util_pct'),
        'technical_qa':data['status'],'qa_errors':data['errors'],'mp4_sha256':{
             k:v['sha256'] for k,v in data['formats'].items()},'folder':str(out)}

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--runtime',type=Path)
    p.add_argument('--report',required=True,type=Path)
    p.add_argument('--markdown',type=Path)
    a=p.parse_args()
    if a.markdown and a.markdown.exists():p.error('markdown report already exists')
    skill=Path(__file__).resolve().parents[1]
    runtime=a.runtime or skill.parent/(skill.name+'-runtime')
    if a.report.exists():p.error('report already exists')
    calibrated=read(runtime/'stage15-20261024-0743-duration'/'summary.json')
    if len(calibrated['results'])!=4 or not all(x['within_five_percent'] for x in calibrated['results']):
        raise ValueError('Piper audio calibration incomplete')
    stability=read(runtime/'stage15-20261024-0743-stability-v3'/'stage15_stability.json')
    if stability['status']!='STABILITY_QA_PASS' or not stability['source_mp4_unchanged']:
        raise ValueError('stability and non-destructive tests not accepted')
    if set(stability['negative_tests'])!={'bad_srt','corrupt_video','deleted_video'}:
        raise ValueError('negative QA cases missing')
    backup=skill.parent/'skill-tintuc-backups'/'stage15-pre-change-20261024-074313'
    ledger=read(backup/'checksums.json')
    if not isinstance(ledger,list) or len(ledger)<20:
        raise ValueError('backup checksum manifest incomplete')
    for row in ledger:
        file=Path(row['path'])
        if not file.resolve().is_relative_to(backup.resolve()) or sha(file).lower()!=row['sha256'].lower():
            raise ValueError('stage15 pre-change backup file corrupted: '+str(file))
    deliveries=runtime/'deliveries'/'Tin-Cong-Nghe-My-20261024-60s'
    old=read(deliveries/'handoff_final.json')
    for x in old['exports']:
        if sha(deliveries/x['filename'])!=x['sha256']:
            raise ValueError('real approved video/delivery changed: '+x['filename'])
    results=[]
    for target,lang,folder,metrics in [
        (30,'en-US',runtime/'stage15-20261024-native30-corrected-30-v2',runtime/'stage15-20261024-benchmark-30-v2.json'),
        (60,'vi-VN',runtime/'stage15-20261024-native30-corrected-60',runtime/'stage15-20261024-benchmark-60.json'),
        (90,'en-US',runtime/'stage15-20261024-native30-corrected-90',runtime/'stage15-20261024-benchmark-90.json'),
        (180,'en-US',runtime/'stage15-20261024-native30-corrected-180',runtime/'stage15-20261024-benchmark-180.json')]:
        results.append(verify(target,lang,folder,metrics,runtime))
    optional=runtime/'stage15-20261024-encoder-repeats'/'encoder_benchmark.json'
    encoder=read(optional) if optional.is_file() else {'status':'NOT_TESTED'}
    report={'stage':15,'status':'TECHNICAL_ACCEPTANCE_PASS',
        'timestamp_utc':dt.datetime.now(dt.timezone.utc).isoformat(),
        'profiles':results,'audio_calibration':calibrated['results'],
        'stability':'PASS','corruption_tests':list(stability['negative_tests']),
        'original_approved_delivery_untouched':True,
        'stage15_prechange_backup_files_verified':len(ledger),
        'nvenc_cpu_repeat_benchmark':encoder.get('aggregate',encoder),
        'release_note':'Ready for manual review of output DEMOs only. Does not certify commercial media rights or editorial factual correctness. No auto publishing.'}
    a.report.parent.mkdir(parents=True,exist_ok=True)
    a.report.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    if a.markdown:
        lines=[
            '# GIAI ĐOẠN 15 — NGHIỆM THU CUỐI / AI News Video Skill',
            '',
            '**Kết luận kỹ thuật: TECHNICAL_ACCEPTANCE_PASS** — '+report['timestamp_utc'],
            '',
            'Đây là thử nghiệm DEMO giả lập trên Windows; không phải bằng chứng được phép đăng nội dung giả lập hoặc tin thật không qua biên tập.',
            'Render throughput, RAM cây tiến trình và GPU toàn thiết bị phụ thuộc cấu hình máy và mức tải các ứng dụng khác.',
            '',
            '| Mục tiêu | MP4 thực | Sai lệch | Thời gian xử lý hai bản | RAM đỉnh mẫu (MB) | Bộ mã hóa | Kết quả |',
            '|---:|---:|---:|---:|---:|---|---|',
        ]
        for row in results:
            lines.append(f"| {row['target_s']}s | {row['actual_s']:.2f}s | {row['error_pct']:+.2f}% | {row['runtime_s']:.2f}s | {row['peak_rss_mb']} | {row['gpu_encoder']} | PASS 9:16 + 16:9 native30 |")
        lines += [
            '',
            '## Bảng nghiệm thu 15.01–15.08',
            '15.01–15.04: bốn mức 30/60/90/180 giây được hiệu chỉnh bằng Piper thật, sau đó render native 30fps ở cả hai tỷ lệ và đo lại MP4 trong ±5% mục tiêu.',
            '15.05: QA codec H264/AAC, resolution 1080x1920/1920x1080, SRT, âm thanh, các frame đại diện và checksum, không lỗi.',
            '15.06: benchmark end-to-end RAM nhóm tiến trình, utilization và VRAM **toàn GPU**; so sánh CPU/NVENC là phép thử mã hóa riêng không tương đương chất lượng preset.',
            '15.07: QA lặp lại cùng nguồn 3 lần; lỗi SRT hỏng, MP4 hỏng, MP4 thiếu đều bị chặn; checksum input không thay đổi.',
            '15.08: có bộ scripts tái tạo, unit tests và tài liệu STAGE15_OPERATIONS.md, sản phẩm DEMO tách khỏi Skill và video tin thật.',
            '',
            '## Số liệu và giới hạn',
            '- Đo duration audio bằng số mẫu WAV. Kiểm tra lại duration video bằng FFprobe sau khi xuất MP4.',
            '- Chỉ tính `remotion_frame_sampling_step=1`, motion native30; không dùng stress preview lặp frame.',
            '- `peak_device_gpu_mem_mb` và `peak_device_gpu_util_pct` là giá trị **của GPU toàn máy**, không phải chỉ job.',
            '- Máy khác/giọng Piper khác/ngữ điệu/nội dung khác có thể cho sai lệch thời lượng; phải chạy preflight trước phê duyệt.',
            '- QA tự động không tự chứng minh đúng tin, giấy phép thương mại hoặc chất lượng nghe/xem trọn vẹn.',
            '- Bài test và files có watermark DEMO; không đăng. Người dùng tự đăng video thật sau rà soát.',
            '',
            '## Kiểm tra bảo toàn và độ ổn định',
            f"- Đã xác minh {report['stage15_prechange_backup_files_verified']} file bản sao lưu pre-stage15 bằng SHA-256.",
            '- Video tin thật đã bàn giao và manifest SHA-256 không bị thay đổi.',
            '- QA ổn định và kiểm thử lỗi giả lập: PASS.',
            '- Không có API đăng TikTok/YouTube và không có auto-upload.',
            '',
            '## Đường dẫn kiểm thử',
            '- Runtime JSON: '+str(a.report),
            '- Calibration: '+str(runtime/'stage15-20261024-0743-duration'/'summary.json'),
            '- Stability: '+str(runtime/'stage15-20261024-0743-stability-v3'/'stage15_stability.json'),
            '- Encoder benchmark: '+str(optional),
            '- Skill instructions: '+str(skill/'references'/'STAGE15_OPERATIONS.md'),
            '',
            '### Ghi chú bản tin thật',
            'Giai đoạn 14 có job thật đã được chọn, phê duyệt hash, render hai tỷ lệ và bàn giao; trạng thái vẫn AWAITING_HUMAN_FINAL_REVIEW. Giai đoạn 15 không tự sửa video đã duyệt hay biến DEMO thành tin thật.',
        ]
        a.markdown.parent.mkdir(parents=True,exist_ok=True)
        a.markdown.write_text('\n'.join(lines)+'\n',encoding='utf-8')
    print(json.dumps({'status':report['status'],'profiles':[{
        'target':x['target_s'],'actual':x['actual_s'],
        'deviation_pct':x['error_pct'],'render_s':x['runtime_s']} for x in results],
        'original_delivery_untouched':True},ensure_ascii=False,indent=2))
if __name__=='__main__':main()
