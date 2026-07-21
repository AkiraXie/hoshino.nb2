# Milky Plugin Coverage Matrix

This matrix tracks behavioral coverage for the registered Milky adapter. A
covered message case builds a Milky `message_receive` event, calls
`MilkyBot.handle_event()`, stubs the registered adapter's `call_http`, and
asserts the emitted action and payload. A module is not counted as covered by
an import, matcher-rule-only test, or a default-disabled service boundary.

The runtime plugin-manager inventory currently contains 27 Hoshino modules
with 91 matchers. Every one of those modules has a representative row below;
the two additional lifecycle-only modules are listed with their dedicated
cross-adapter tests.

## Message Plugins

| Module | Representative entry | Status | Behavioral test |
| --- | --- | --- | --- |
| `base.black` | `拉黑` interactive command | covered | `TestBlackPlugin.test_black_superuser_starts_interactive_prompt` |
| `base.broadcast` | `bc` superuser command | covered | `TestBasePlugins.test_broadcast_superuser_sends_to_joined_group` |
| `base.cookies` | `check_cookies` superuser command | covered | `TestBasePlugins.test_check_cookies_superuser_mention_reports_empty` |
| `base.help` | `help` Alconna command | covered | `TestBasePlugins.test_help_command_responds` |
| `base.image` | short delete command and reaction notice | covered | `TestBasePlugins.test_image_short_delete_alias_remains_available`, `test_image_reaction_notice_saves_referenced_image` |
| `base.listenmeta` | bot-connect hook | lifecycle covered separately | `nb-tests/test_plugin_event_lifecycle.py::test_listenmeta_bot_connect_notifies_superusers_on_both_adapters` |
| `base.ls` | superuser `ls.group` command | covered | `TestBasePlugins.test_ls_group_superuser_reports_joined_groups` |
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
| `information.resolve` | BV message resolver | covered | `TestInformationPlugins.test_resolve_bv_dispatches_stubbed_video` |
| `information.weibo` | enabled list command and cached reaction notice | covered | `TestInformationPlugins.test_weibo_enabled_empty_list_responds`, `test_weibo_reaction_notice_uses_cached_post` |
| `interactive.QA` | group question list | covered | `TestInteractivePlugins.test_qa_group_list_responds` |
| `interactive.alisten` | enabled missing-config response | covered | `TestInteractivePlugins.test_alisten_enabled_missing_config_responds` |
| `interactive.chooseone` | group and friend commands | covered | `TestInteractivePlugins.test_chooseone_alconna_responds`, `test_chooseone_private_responds` |
| `interactive.emojimix` | enabled two-emoji message | covered | `TestInteractivePlugins.test_emojimix_enabled_text_sends_image` |
| `interactive.foods` | enabled text and image output | covered | `TestInteractivePlugins.test_foods_enabled_text_image` |
| `interactive.qbitorrent` | enabled missing-config response | covered | `TestInteractivePlugins.test_qbitorrent_enabled_missing_config_responds` |
| `interactive.steam` | enabled list command | covered | `TestInteractivePlugins.test_steam_enabled_list_responds` |
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
- Wildcard services use native NoneBot message matchers, so `resolve`, `QA`,
  and `emojimix` evaluate their own rules independently instead of sharing an
  Alconna wildcard parser result.
