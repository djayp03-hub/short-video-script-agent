"""Reproduce bounded offline conversation cases and audit actual Agent artifacts."""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'src'))
from video_agent.chat import ChatService
from video_agent.cli import read, write
from verify_artifacts import verify


def main():
    parser = argparse.ArgumentParser(description='离线多轮对话验收，不调用真实模型')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    output = args.output or ROOT/'runs'/('chat-eval-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    service = ChatService(output, read(ROOT/'data/materials.json'), read(ROOT/'data/brand_rules.json'))
    report = []

    def turn(ident, case, message, expected, attachments=None):
        result = service.send(ident, message, attachments)
        status = result['result']['status'] if result['result'] else 'conversation_only'
        folder = Path(result['artifact_dir'])
        audit = verify(folder) if (folder/'run.json').exists() else []
        report.append({'case':case, 'input':message, 'expected':expected, 'actual':status,
                       'passed':status == expected and not audit,
                       'estimated_seconds':(result['result'] or {}).get('estimated_total_seconds'),
                       'record':folder.relative_to(output).as_posix(), 'artifact_errors':audit})

    ident = service.create_session('mock')['id']
    turn(ident, 'missing_requirements', '介绍剪映盒演示版字幕，30秒', 'conversation_only')
    turn(ident, 'complete_after_followup', '受众：学生\n平台：抖音\n风格：清晰自然', 'completed')
    turn(ident, 'shorten_and_recheck', '缩短到15秒', 'completed')
    turn(ident, 'unsupported_offline_style', '风格：活泼', 'incomplete')
    ident = service.create_session('mock')['id']
    turn(ident, 'missing_material', '产品：校园便签\n主题：便签介绍\n受众：学生\n平台：抖音\n时长：30秒\n风格：自然', 'needs_input')
    turn(ident, 'resume_after_material', '我补充了资料，请继续生成', 'completed',
         [{'product':'校园便签', 'text':'校园便签支持本地保存文字。'}])
    summary = {'mode':'mock', 'scope':'离线对话机制与产物一致性，不代表真实模型效果',
               'total':len(report), 'passes':sum(r['passed'] for r in report), 'cases':report}
    write(output/'summary.json', summary)
    print(json.dumps(summary, ensure_ascii=False))
    return 0 if all(r['passed'] for r in report) else 1


if __name__ == '__main__':
    raise SystemExit(main())
