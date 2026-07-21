# Milky Plugin Coverage Matrix

This matrix tracks behavioral coverage for the registered Milky adapter. A
covered message case builds a Milky `message_receive` event, calls
`MilkyBot.handle_event()`, stubs the registered adapter's `call_http`, and
asserts the emitted action and payload. A module is not counted as covered by
an import, matcher-rule-only test, or a default-disabled service boundary.

## Message Plugins

| Module | Representative entry | Status | Behavioral test |
| --- | --- | --- | --- |
| `base.black` | `拉黑` interactive command | covered | `TestBlackPlugin.test_black_superuser_starts_interactive_prompt` |
| `base.broadcast` | `bc` superuser command | covered | `TestBasePlugins.test_broadcast_superuser_sends_to_joined_group` |
| `base.cookies` | `check_cookies` superuser command | covered | `TestBasePlugins.test_check_cookies_superuser_mention_reports_empty` |
| `base.help` | `help` Alconna command | covered | `TestBasePlugins.test_help_command_responds` |
| `base.image` | keyword and reaction notice paths | lifecycle covered separately | `nb-tests/test_milky_adapter.py::test_image_reaction_business_rule_is_adapter_neutral`; no Milky notice dispatch fixture yet |
| `base.listenmeta` | bot-connect hook | lifecycle covered separately | `nb-tests/test_plugin_event_lifecycle.py::test_listenmeta_bot_connect_notifies_superusers_on_both_adapters` |
| `base.ls` | superuser `ls` command group | not yet covered | needs a real Milky superuser command event |
| `base.service_manage` | `lssv` ADMIN + mention | covered | `TestBasePlugins.test_lssv_superuser_mention_reports_services` |
| `base.test` | `testmatchers` superuser command | covered | `TestBasePlugins.test_testmatchers_superuser_mention_responds` |
| `base.zai` | mention command | covered | `TestBasePlugins.test_zai_at_mention_zai_text` |
| `develop.echoandsay` | `say` Alconna command | covered | `TestDevelopPlugins.test_say_alconna_responds` |
| `develop.healthchecker` | HTTP health endpoint | lifecycle covered separately | `nb-tests/test_plugin_event_lifecycle.py::test_healthcheck_reports_adapter_bot_connectivity` |
| `develop.server_info` | `状态` superuser command | covered | `TestDevelopPlugins.test_server_info_superuser_responds` |
| `entertainment.bihua` | enabled `bihua` image output | covered | `TestEntertainmentPlugins.test_bihua_enabled_sends_image` |
| `entertainment.coser` | enabled mention command | covered | `TestEntertainmentPlugins.test_coser_enabled_mention_sends_image` |
| `entertainment.dice` | regex match and negative input | covered | `TestEntertainmentPlugins.test_dice_regex_responds` |
| `information.bilireq` | enabled list command | covered | `TestInformationPlugins.test_bilireq_enabled_empty_list_responds` |
| `information.pushlive` | enabled list command | covered | `TestInformationPlugins.test_pushlive_enabled_empty_list_responds` |
| `information.resolve` | URL message resolver | rule covered separately | `nb-tests/test_plugin_event_lifecycle.py::test_resolve_rule_recognizes_bilibili_links_on_both_adapters`; full Milky dispatch remains uncovered |
| `information.weibo` | enabled list command and reaction notice | partially covered | `TestInformationPlugins.test_weibo_enabled_empty_list_responds`; reaction business rule is in `test_milky_adapter.py` |
| `interactive.QA` | group question list | covered | `TestInteractivePlugins.test_qa_group_list_responds` |
| `interactive.alisten` | enabled missing-config response | covered | `TestInteractivePlugins.test_alisten_enabled_missing_config_responds` |
| `interactive.chooseone` | group and friend commands | covered | `TestInteractivePlugins.test_chooseone_alconna_responds`, `test_chooseone_private_responds` |
| `interactive.emojimix` | two-emoji message | not yet covered | needs a Milky segment fixture that satisfies `EventMessage` and `PlainText` together |
| `interactive.foods` | enabled text and image output | covered | `TestInteractivePlugins.test_foods_enabled_text_image` |
| `interactive.qbitorrent` | enabled missing-config response | covered | `TestInteractivePlugins.test_qbitorrent_enabled_missing_config_responds` |
| `interactive.steam` | list command | not yet covered | current synthetic Alconna event does not enter the matcher; needs a valid Milky command fixture |
| `tools.b64` | enabled group and friend commands | covered | `TestToolsPlugins.test_b64_enabled_encrypt_text`, `test_b64_enabled_encrypt_private_text` |
| `tools.nbnhhsh` | regex group, negative, and friend cases | covered | `TestToolsPlugins.test_nbnhhsh_regex_matches_stubbed`, `test_nbnhhsh_private_responds` |

## Harness Rules

- Group events use `peer_id=group_id`; friend events use `peer_id=sender_id`
  and contain the required Milky friend object.
- The shared capture patches `MilkyAdapter.call_http`, the registered adapter
  HTTP boundary. It records ordered action and parameter records.
- The shared outbound HTTP stubs patch `post`, `get`, and `head` directly. A
  failed import or patch fails the test instead of allowing live traffic.
- Services with `enable_on_default=False` are explicitly enabled by a scoped
  monkeypatch in positive behavior cases.
