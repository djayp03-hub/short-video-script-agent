import importlib.util
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
from video_agent.cli import read

FULL = '介绍剪映盒演示版的字幕功能，给学生看，发抖音，30秒，清晰自然。'


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(importlib.util.find_spec('video_agent.chat'), '多轮会话功能尚未实现')
        from video_agent.chat import ChatService, ChatError
        self.ChatService, self.ChatError = ChatService, ChatError
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.folder = Path(self.temp.name)
        self.materials, self.rules = read(ROOT/'data/materials.json'), read(ROOT/'data/brand_rules.json')
        self.service = ChatService(self.folder, self.materials, self.rules)
        self.session = self.service.create_session('mock')['id']

    def test_missing_requirements_are_not_invented_and_followup_completes(self):
        first = self.service.send(self.session, '介绍剪映盒演示版字幕，30秒')
        self.assertEqual(first['request']['target_seconds'], 30)
        self.assertNotIn('audience', first['request'])
        self.assertIsNone(first['result'])
        second = self.service.send(self.session, '受众：学生\n平台：抖音\n风格：清晰自然')
        self.assertEqual(second['result']['status'], 'completed')
        self.assertEqual(second['request']['product'], '剪映盒演示版')
        self.assertEqual(len(second['messages']), 4)

    def test_shortening_rechecks_the_new_turn_and_labels_previous_draft(self):
        one = self.service.send(self.session, FULL)
        two = self.service.send(self.session, '缩短到15秒')
        self.assertEqual(two['result']['status'], 'completed')
        self.assertLessEqual(two['result']['estimated_total_seconds'], 15)
        self.assertNotEqual(one['artifact_dir'], two['artifact_dir'])
        run = read(Path(two['artifact_dir'])/'run.json')
        self.assertFalse(run['initial_draft_fixture'])
        self.assertEqual(run['initial_draft_kind'], 'conversation_previous_draft')
        self.assertTrue(any(t.get('decision', {}).get('action')=='estimate_duration' for t in two['trace']))

    def test_sessions_and_product_changes_do_not_reuse_other_drafts(self):
        self.service.send(self.session, FULL)
        other = self.service.create_session('mock')
        self.assertEqual(other['request'], {})
        changed = self.service.send(self.session, '产品：剪映盒专业版\n主题：自动字幕介绍')
        self.assertEqual(changed['result']['status'], 'completed')
        self.assertEqual({s['id'] for s in changed['result']['sources']}, {'D01'})
        self.assertFalse(read(Path(changed['artifact_dir'])/'run.json')['initial_draft_fixture'])
        self.assertIsNone(read(Path(changed['artifact_dir'])/'run.json')['initial_draft_kind'])

    def test_user_materials_are_retrievable_and_isolated(self):
        custom = self.service.send(self.session,
            '产品：校园便签\n主题：便签功能介绍\n受众：学生\n平台：抖音\n时长：30秒\n风格：自然',
            attachments=[{'product':'校园便签','text':'校园便签支持本地保存文字。'}])
        self.assertEqual(custom['result']['status'], 'completed')
        source = custom['result']['sources'][0]
        self.assertTrue(source['user_provided'])
        self.assertEqual(source['text'], '校园便签支持本地保存文字。')
        self.assertEqual(len(self.service.get_session(self.session)['attachments']), 1)
        self.assertEqual(self.service.create_session('mock')['attachments'], [])

    def test_refresh_and_service_restart_restore_conversation(self):
        self.service.send(self.session, '介绍剪映盒演示版字幕，30秒')
        restart = self.ChatService(self.folder, self.materials, self.rules)
        saved = restart.get_session(self.session)
        self.assertEqual(saved['request']['target_seconds'], 30)
        self.assertEqual(len(saved['messages']), 2)
        resumed = restart.send(self.session, '受众：学生\n平台：抖音\n风格：自然')
        self.assertEqual(resumed['result']['status'], 'completed')

    def test_real_missing_key_is_explicit_and_never_runs_mock(self):
        session = self.service.create_session('real')['id']
        with patch.dict(os.environ, {'VIDEO_API_KEY':'','DASHSCOPE_API_KEY':''}):
            response = self.service.send(session, FULL)
        self.assertEqual(response['mode'], 'real')
        self.assertEqual(response['result']['status'], 'failed')
        self.assertEqual(response['result']['reason'], 'missing_api_key')
        self.assertEqual(response['trace'], [])
        self.assertTrue((Path(response['artifact_dir'])/'dialogue.json').exists())

    def test_invalid_model_plan_does_not_commit_corrupt_requirements(self):
        class InvalidRouter:
            calls = []
            def plan(self, *args):
                return {'reply':'继续','request':{'target_seconds':True},'run':True,'use_previous_draft':False}
        service = self.ChatService(self.folder, self.materials, self.rules, router_factory=lambda mode:InvalidRouter())
        session = service.create_session('real')['id']
        response = service.send(session, FULL)
        self.assertEqual(response['request'], {})
        self.assertEqual(response['result']['status'], 'failed')
        self.assertEqual(response['result']['reason'], 'invalid_chat_plan')

    def test_unsupported_offline_edit_does_not_claim_success(self):
        self.service.send(self.session, FULL)
        response = self.service.send(self.session, '给标题加一个押韵的双关语')
        self.assertIsNone(response['result'])
        self.assertIn('真实模式', response['messages'][-1]['content'])

    def test_ids_message_size_and_attachment_structure_are_validated(self):
        for ident in ['../outside','x'*32,'../../.env']:
            with self.assertRaises(self.ChatError):
                self.service.get_session(ident)
        for message in ['', 'x'*4001, {'message':'x'}]:
            with self.assertRaises(self.ChatError):
                self.service.send(self.session, message)
        with self.assertRaises(self.ChatError):
            self.service.send(self.session, '补充资料', attachments=[{'product':'校园便签','text':''}])

    def test_greeting_does_not_generate_a_script(self):
        response = self.service.send(self.session, '你好')
        self.assertIsNone(response['result'])
        self.assertEqual(response['request'], {})
        self.assertEqual(response['trace'], [])

    def test_changed_theme_starts_fresh_even_for_same_product(self):
        self.service.send(self.session, FULL)
        response = self.service.send(self.session, '主题：视频裁剪介绍')
        metadata = read(Path(response['artifact_dir'])/'run.json')
        self.assertIsNone(metadata['initial_draft_kind'])

    def test_conversation_only_turn_retains_an_explicit_previous_result(self):
        self.service.send(self.session, FULL)
        response = self.service.send(self.session, '你好')
        self.assertIsNone(response['result'])
        self.assertEqual(response['reference_result']['status'], 'completed')
        self.assertEqual(response['trace'], [])

    def test_turn_budget_stops_additional_requests_without_losing_history(self):
        for _ in range(40):
            self.service.send(self.session, '你好')
        with self.assertRaises(self.ChatError) as failure:
            self.service.send(self.session, '还有问题')
        self.assertEqual(failure.exception.code, 'turn_limit')
        self.assertEqual(len(self.service.get_session(self.session)['messages']), 80)

    def test_material_question_can_resume_after_attaching_evidence(self):
        first = self.service.send(self.session,
            '产品：校园便签\n主题：便签介绍\n受众：学生\n平台：抖音\n时长：30秒\n风格：自然')
        self.assertEqual(first['result']['status'], 'needs_input')
        resumed = self.service.send(self.session, '我补充了资料，请继续生成',
            attachments=[{'product':'校园便签','text':'校园便签支持本地保存文字。'}])
        self.assertIsNotNone(resumed['result'])
        self.assertEqual(resumed['result']['status'], 'completed')

    def test_interrupted_turn_is_marked_incomplete_after_service_restart(self):
        class InterruptedRouter:
            calls = []
            def plan(self, *args):
                raise KeyboardInterrupt()
        service = self.ChatService(self.folder, self.materials, self.rules,
                                   router_factory=lambda mode:InterruptedRouter())
        session = service.create_session('mock')['id']
        with self.assertRaises(KeyboardInterrupt):
            service.send(session, FULL)
        restarted = self.ChatService(self.folder, self.materials, self.rules)
        restored = restarted.get_session(session)
        self.assertIsNotNone(restored['result'])
        self.assertEqual(restored['result']['status'], 'incomplete')
        self.assertEqual(restored['result']['reason'], 'interrupted')
        self.assertEqual(len(restored['messages']), 2)
        self.assertEqual(restarted.send(session, FULL)['result']['status'], 'completed')

    def test_offline_style_edit_does_not_accept_an_unchanged_draft(self):
        first = self.service.send(self.session, FULL)
        changed = self.service.send(self.session, '风格：活泼')
        self.assertNotEqual(changed['result']['status'], 'completed')
        self.assertEqual(changed['result']['draft'], first['result']['draft'])

    def test_conversation_reply_does_not_require_a_complete_generation_brief(self):
        class ExplanationRouter:
            calls = []
            def plan(self, *args):
                return {'reply':'这个项目可以检索资料、估时和检查规则。', 'request':{},
                        'run':False, 'use_previous_draft':False}
        service = self.ChatService(self.folder, self.materials, self.rules,
                                   router_factory=lambda mode:ExplanationRouter())
        session = service.create_session('real')['id']
        response = service.send(session, '这个项目能做什么？')
        self.assertEqual(response['messages'][-1]['content'], '这个项目可以检索资料、估时和检查规则。')
        self.assertIsNone(response['result'])


if __name__ == '__main__':
    unittest.main()
