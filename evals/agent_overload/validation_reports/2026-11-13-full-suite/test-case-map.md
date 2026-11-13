# Executed test cases and scenarios, 2026-11-13

272 backend tests and five frontend checks passed. The table maps every executed test to its intended scenario. Descriptions summarize the test contract, not claims of live-model quality. Short B/F identifiers are local to this report; exact Python test identities remain authoritative.

The backend runner configures disposable storage, dummy credentials and legacy settings before importing the application. Individual bounded tests choose bounded settings; fresh-process default tests verify shipped defaults. This is not a complete configuration matrix.

## The requested dormant-worker example

`test_old_worker_is_findable_outside_recent_entries` proves backend retrieval outside the recent list. `test_real_lookup_loop_uses_selected_ranker_with_bounded_preflight` proves a scripted Interaction Agent can actually execute the lookup tool. Live scenario A (`dormant-owner`, bounded) supplies the separate real-model decision evidence: the worker is absent from its five-entry recent roster, the model calls find_worker, then dispatches `2023 tax documents`. These layers should not be conflated.

## test_agent_overload_comparison.py — 7 passed

Paired-comparison grading, real-path capture, usage completeness, limits and partial evidence.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B001 | Endpoint size call limits and error redaction precede public evidence. | [ComparisonCaptureTests.test_endpoint_size_call_limits_and_error_redaction_precede_public_evidence](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:51) | Passed |
| B002 | Exhaust the evaluation provider-call cap, retain completed/partial traces and mark unrun cases unavailable instead of inventing zero-quality observations. | [ComparisonCliTests.test_call_exhaustion_keeps_partial_evidence_and_marks_unrun_cases_unavailable](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:137) | Passed |
| B003 | Live missing key and invalid controls fail without network or evidence. | [ComparisonCliTests.test_live_missing_key_and_invalid_controls_fail_without_network_or_evidence](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:151) | Passed |
| B004 | Run paired scripted agents through actual application paths with fixed model/output settings, isolated private data, separate gold labels, exact fake effects and artifact hashes. | [ComparisonCliTests.test_paired_actual_paths_keep_models_inputs_effects_provenance_and_private_data_separate](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:89) | Passed |
| B005 | Missing invalid and real zero usage are not interchangeable. | [ComparisonUsageTests.test_missing_invalid_and_real_zero_usage_are_not_interchangeable](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:27) | Passed |
| B006 | A live-mode run without completed decisions reports routing quality unavailable rather than a valid zero-accuracy result. | [ComparisonUsageTests.test_no_completed_live_decisions_have_no_routing_quality_measurement](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:41) | Passed |
| B007 | Keep an observed routing decision gradable even if worker/callback completion fails later; unavailable routing remains distinct from an observed wrong choice. | [ComparisonUsageTests.test_observed_routing_remains_gradable_after_a_later_task_failure](D:/personal_projects/openpoke/server/tests/test_agent_overload_comparison.py:19) | Passed |

## test_agent_overload_evaluation.py — 8 passed

Baseline capture, deterministic grading, frozen inputs, isolation and artifact preservation.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B008 | CLI captures full roster inputs and trace with isolated safe evidence. | [EvaluationCliTests.test_cli_captures_full_roster_inputs_and_trace_with_isolated_safe_evidence](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:119) | Passed |
| B009 | Fixture drift fails instead of publishing a passing report. | [EvaluationCliTests.test_fixture_drift_fails_instead_of_publishing_a_passing_report](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:199) | Passed |
| B010 | Invalid or live modes fail before a run is created. | [EvaluationCliTests.test_invalid_or_live_modes_fail_before_a_run_is_created](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:185) | Passed |
| B011 | Repeated runs keep input fingerprints and never overwrite evidence. | [EvaluationCliTests.test_repeated_runs_keep_input_fingerprints_and_never_overwrite_evidence](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:171) | Passed |
| B012 | Manifest rejects credentials unpinned modes and invalid limits. | [EvaluationGradingTests.test_manifest_rejects_credentials_unpinned_modes_and_invalid_limits](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:81) | Passed |
| B013 | Report observations preserve four states and require evidence. | [EvaluationGradingTests.test_report_observations_preserve_four_states_and_require_evidence](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:67) | Passed |
| B014 | Routing grades action all owners and wrong reuse separately. | [EvaluationGradingTests.test_routing_grades_action_all_owners_and_wrong_reuse_separately](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:20) | Passed |
| B015 | Task grading uses exact write evidence and rejects extra recipients. | [EvaluationGradingTests.test_task_grading_uses_exact_write_evidence_and_rejects_extra_recipients](D:/personal_projects/openpoke/server/tests/test_agent_overload_evaluation.py:37) | Passed |

## test_agent_overload_fixtures.py — 7 passed

Synthetic catalog, routing and mailbox fixture integrity.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B016 | Cases cover revised contracts without leaking gold into profiles. | [CatalogFixtureTests.test_cases_cover_revised_contracts_without_leaking_gold_into_profiles](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:42) | Passed |
| B017 | Catalog sizes ids and content match frozen fingerprints. | [CatalogFixtureTests.test_catalog_sizes_ids_and_content_match_frozen_fingerprints](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:15) | Passed |
| B018 | Comparisons change one declared factor at a time. | [CatalogFixtureTests.test_comparisons_change_one_declared_factor_at_a_time](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:86) | Passed |
| B019 | Core resource bindings resolve to the correct fixture mailbox. | [CatalogFixtureTests.test_core_resource_bindings_resolve_to_the_correct_fixture_mailbox](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:73) | Passed |
| B020 | Current legacy prompt still contains the entire fixture roster. | [CatalogFixtureTests.test_current_legacy_prompt_still_contains_the_entire_fixture_roster](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:95) | Passed |
| B021 | Fixture loads are independent and reject unfrozen sizes or paths. | [CatalogFixtureTests.test_fixture_loads_are_independent_and_reject_unfrozen_sizes_or_paths](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:32) | Passed |
| B022 | Stale card and dormant owner are explicit test inputs. | [CatalogFixtureTests.test_stale_card_and_dormant_owner_are_explicit_test_inputs](D:/personal_projects/openpoke/server/tests/test_agent_overload_fixtures.py:62) | Passed |

## test_agent_overload_tasks.py — 5 passed

Evaluation-owned background tasks, cancellation, deadlines and propagation of real failures.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B023 | A cancelled child connection task does not abort evaluation draining of actual worker/callback tasks. | [EvaluationTaskTests.test_cancelled_background_child_does_not_abort_worker_and_callback_drain](D:/personal_projects/openpoke/server/tests/test_agent_overload_tasks.py:10) | Passed |
| B024 | Cancellation of the evaluation drain itself still propagates and cancels its pending worker. | [EvaluationTaskTests.test_cancelling_the_drain_still_propagates_and_cleans_up_pending_work](D:/personal_projects/openpoke/server/tests/test_agent_overload_tasks.py:48) | Passed |
| B025 | An evaluation case deadline still raises TimeoutError and cancels pending work. | [EvaluationTaskTests.test_case_deadline_still_times_out_and_cancels_pending_work](D:/personal_projects/openpoke/server/tests/test_agent_overload_tasks.py:66) | Passed |
| B026 | A task may return an exception object as data without being mistaken for a task that raised an exception. | [EvaluationTaskTests.test_exception_return_value_is_not_mistaken_for_a_task_failure](D:/personal_projects/openpoke/server/tests/test_agent_overload_tasks.py:74) | Passed |
| B027 | Preserve and raise a real background exception even when a different child was cancelled. | [EvaluationTaskTests.test_real_background_failure_is_preserved_alongside_cancelled_child](D:/personal_projects/openpoke/server/tests/test_agent_overload_tasks.py:32) | Passed |

## test_bounded_application.py — 6 passed

ASGI HTTP, actual agent/callback paths, exact large draft, triggers, lifecycle and clear.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B028 | Exercise FastAPI lifespan, health and scheduler start/stop with the watcher lifecycle interface stubbed; this is not a live mailbox poll. | [BoundedApplicationTests.test_application_lifecycle_starts_and_stops_existing_background_services](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:317) | Passed |
| B029 | Exercise real ASGI chat routes: reject invalid inputs without model work and return 202 for valid input while background model work remains blocked. | [BoundedApplicationTests.test_http_acceptance_is_async_and_invalid_submissions_do_not_call_provider](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:125) | Passed |
| B030 | Exercise actual HTTP and both scripted agents with a draft over 256 KiB: full review, separate confirmation, exact fake send, opt-out/re-enable, clear and a rejected late callback. | [BoundedApplicationTests.test_http_large_review_confirmation_callbacks_and_clear_preserve_exact_content](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:166) | Passed |
| B031 | A scripted provider 503 after HTTP acceptance must become a user-visible failure reply in history. | [BoundedApplicationTests.test_http_provider_failure_becomes_a_visible_history_reply](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:150) | Passed |
| B032 | Create a real SQLite trigger owned by one worker, reject cross-owner access, poll controlled due times once per in-flight run and deliver real callbacks; advance recurring schedules. | [BoundedApplicationTests.test_owned_triggers_poll_once_advance_recurrence_and_deliver_real_callbacks](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:252) | Passed |
| B033 | Inspect actual SQLite connections after successful reads and failing parameter binding; both must be closed. | [BoundedApplicationTests.test_trigger_store_releases_connections_after_success_and_failure](D:/personal_projects/openpoke/server/tests/test_bounded_application.py:103) | Passed |

## test_chat_failures.py — 4 passed

Visible asynchronous chat failures and successful reply behavior.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B034 | Failed result is visible in chat. | [ChatFailureTests.test_failed_result_is_visible_in_chat](D:/personal_projects/openpoke/server/tests/test_chat_failures.py:35) | Passed |
| B035 | Runtime logs provider error and traceback. | [ChatFailureTests.test_runtime_logs_provider_error_and_traceback](D:/personal_projects/openpoke/server/tests/test_chat_failures.py:62) | Passed |
| B036 | Success does not add a duplicate reply. | [ChatFailureTests.test_success_does_not_add_a_duplicate_reply](D:/personal_projects/openpoke/server/tests/test_chat_failures.py:54) | Passed |
| B037 | Unexpected exception is visible in chat. | [ChatFailureTests.test_unexpected_exception_is_visible_in_chat](D:/personal_projects/openpoke/server/tests/test_chat_failures.py:46) | Passed |

## test_content_store.py — 23 passed

Immutable exact sources, provenance, publication, restart and generation invalidation.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B038 | Capture failure after Gmail result does not continue tool loop. | [ContentCaptureTests.test_capture_failure_after_gmail_result_does_not_continue_tool_loop](D:/personal_projects/openpoke/server/tests/test_content_store.py:329) | Passed |
| B039 | Clear route invalidates content and removes only managed content. | [ContentCaptureTests.test_clear_route_invalidates_content_and_removes_only_managed_content](D:/personal_projects/openpoke/server/tests/test_content_store.py:317) | Passed |
| B040 | Concurrent capture scopes keep owner identity separate. | [ContentCaptureTests.test_concurrent_capture_scopes_keep_owner_identity_separate](D:/personal_projects/openpoke/server/tests/test_content_store.py:346) | Passed |
| B041 | Draft review keeps exact body and unknown mailbox provenance. | [ContentCaptureTests.test_draft_review_keeps_exact_body_and_unknown_mailbox_provenance](D:/personal_projects/openpoke/server/tests/test_content_store.py:267) | Passed |
| B042 | Gmail capture uses the executed account without changing result. | [ContentCaptureTests.test_gmail_capture_uses_the_executed_account_without_changing_result](D:/personal_projects/openpoke/server/tests/test_content_store.py:227) | Passed |
| B043 | Inner email search preserves raw result before cleaning. | [ContentCaptureTests.test_inner_email_search_preserves_raw_result_before_cleaning](D:/personal_projects/openpoke/server/tests/test_content_store.py:239) | Passed |
| B044 | Large chat and callback messages are captured without previews. | [ContentCaptureTests.test_large_chat_and_callback_messages_are_captured_without_previews](D:/personal_projects/openpoke/server/tests/test_content_store.py:247) | Passed |
| B045 | Legacy mode and unscoped helpers do not create content. | [ContentCaptureTests.test_legacy_mode_and_unscoped_helpers_do_not_create_content](D:/personal_projects/openpoke/server/tests/test_content_store.py:339) | Passed |
| B046 | Mixed batch retains its first generation for callback. | [ContentCaptureTests.test_mixed_batch_retains_its_first_generation_for_callback](D:/personal_projects/openpoke/server/tests/test_content_store.py:304) | Passed |
| B047 | Queued task inherits old generation and cannot capture after clear. | [ContentCaptureTests.test_queued_task_inherits_old_generation_and_cannot_capture_after_clear](D:/personal_projects/openpoke/server/tests/test_content_store.py:280) | Passed |
| B048 | Stale callback is rejected even if its body is small. | [ContentCaptureTests.test_stale_callback_is_rejected_even_if_its_body_is_small](D:/personal_projects/openpoke/server/tests/test_content_store.py:294) | Passed |
| B049 | Worker journal preserves content before its existing truncation. | [ContentCaptureTests.test_worker_journal_preserves_content_before_its_existing_truncation](D:/personal_projects/openpoke/server/tests/test_content_store.py:214) | Passed |
| B050 | Clear invalidates refs and rejects old writes without touching other files. | [ContentStoreTests.test_clear_invalidates_refs_and_rejects_old_writes_without_touching_other_files](D:/personal_projects/openpoke/server/tests/test_content_store.py:86) | Passed |
| B051 | Corrupt or removed generation is not silently reinitialized. | [ContentStoreTests.test_corrupt_or_removed_generation_is_not_silently_reinitialized](D:/personal_projects/openpoke/server/tests/test_content_store.py:127) | Passed |
| B052 | Empty content and distinct captures have distinct immutable refs. | [ContentStoreTests.test_empty_content_and_distinct_captures_have_distinct_immutable_refs](D:/personal_projects/openpoke/server/tests/test_content_store.py:79) | Passed |
| B053 | Failed cleanup still invalidates history. | [ContentStoreTests.test_failed_cleanup_still_invalidates_history](D:/personal_projects/openpoke/server/tests/test_content_store.py:101) | Passed |
| B054 | Failed publication does not leave a readable partial object. | [ContentStoreTests.test_failed_publication_does_not_leave_a_readable_partial_object](D:/personal_projects/openpoke/server/tests/test_content_store.py:138) | Passed |
| B055 | Fresh process can read content from its original root. | [ContentStoreTests.test_fresh_process_can_read_content_from_its_original_root](D:/personal_projects/openpoke/server/tests/test_content_store.py:159) | Passed |
| B056 | Full Unicode text and middle fact round trip in bounded byte pages. | [ContentStoreTests.test_full_unicode_text_and_middle_fact_round_trip_in_bounded_byte_pages](D:/personal_projects/openpoke/server/tests/test_content_store.py:44) | Passed |
| B057 | Invalid refs bounds missing and truncated content fail explicitly. | [ContentStoreTests.test_invalid_refs_bounds_missing_and_truncated_content_fail_explicitly](D:/personal_projects/openpoke/server/tests/test_content_store.py:111) | Passed |
| B058 | Profiles and concurrent appends remain separate. | [ContentStoreTests.test_profiles_and_concurrent_appends_remain_separate](D:/personal_projects/openpoke/server/tests/test_content_store.py:144) | Passed |
| B059 | Restart preserves refs and qualification. | [ContentStoreTests.test_restart_preserves_refs_and_qualification](D:/personal_projects/openpoke/server/tests/test_content_store.py:61) | Passed |
| B060 | Unknown mailbox never inherits a known account. | [ContentStoreTests.test_unknown_mailbox_never_inherits_a_known_account](D:/personal_projects/openpoke/server/tests/test_content_store.py:71) | Passed |

## test_context_budget.py — 16 passed

Complete-request estimates, configuration, preserved wire data and rejection before HTTP.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B061 | Fitting request preserves content tools output and actual usage. | [ContextBudgetProviderTests.test_fitting_request_preserves_content_tools_output_and_actual_usage](D:/personal_projects/openpoke/server/tests/test_context_budget.py:142) | Passed |
| B062 | Growing tool results are rechecked on every call. | [ContextBudgetProviderTests.test_growing_tool_results_are_rechecked_on_every_call](D:/personal_projects/openpoke/server/tests/test_context_budget.py:215) | Passed |
| B063 | Missing provider usage stays unknown despite local estimate. | [ContextBudgetProviderTests.test_missing_provider_usage_stays_unknown_despite_local_estimate](D:/personal_projects/openpoke/server/tests/test_context_budget.py:206) | Passed |
| B064 | Reject an oversized complete request before HTTP setup, with no prompt or credential text in the budget error. | [ContextBudgetProviderTests.test_oversized_request_does_not_open_http_or_expose_private_content](D:/personal_projects/openpoke/server/tests/test_context_budget.py:162) | Passed |
| B065 | Exercise the five actual model-calling paths and classifier construction with required input that cannot fit; reject before network work. | [ContextBudgetProviderTests.test_real_callers_and_classifier_builder_reject_oversized_input_before_http](D:/personal_projects/openpoke/server/tests/test_context_budget.py:236) | Passed |
| B066 | Summarizer does not retry a deterministic budget error. | [ContextBudgetProviderTests.test_summarizer_does_not_retry_a_deterministic_budget_error](D:/personal_projects/openpoke/server/tests/test_context_budget.py:227) | Passed |
| B067 | Unknown model and unsupported media cannot bypass preflight. | [ContextBudgetProviderTests.test_unknown_model_and_unsupported_media_cannot_bypass_preflight](D:/personal_projects/openpoke/server/tests/test_context_budget.py:178) | Passed |
| B068 | Send exactly the immutable bytes checked by preflight even if a caller mutates its original message data during client setup. | [ContextBudgetProviderTests.test_wire_snapshot_cannot_grow_while_http_client_opens](D:/personal_projects/openpoke/server/tests/test_context_budget.py:187) | Passed |
| B069 | Include system instructions, messages, history, tool schemas, arguments/results and request metadata in preflight without altering accepted content. | [ContextBudgetTests.test_all_input_sections_are_counted_and_preserved](D:/personal_projects/openpoke/server/tests/test_context_budget.py:49) | Passed |
| B070 | Configuration rejects invalid flags values and reservations. | [ContextBudgetTests.test_configuration_rejects_invalid_flags_values_and_reservations](D:/personal_projects/openpoke/server/tests/test_context_budget.py:125) | Passed |
| B071 | Configuration requires explicit allowances for every selected model. | [ContextBudgetTests.test_configuration_requires_explicit_allowances_for_every_selected_model](D:/personal_projects/openpoke/server/tests/test_context_budget.py:116) | Passed |
| B072 | A request exactly at the configured estimated boundary passes; one estimate unit over fails. | [ContextBudgetTests.test_exact_estimated_boundary_passes_and_one_over_is_rejected](D:/personal_projects/openpoke/server/tests/test_context_budget.py:74) | Passed |
| B073 | Invalid allowances and unsupported media fail explicitly. | [ContextBudgetTests.test_invalid_allowances_and_unsupported_media_fail_explicitly](D:/personal_projects/openpoke/server/tests/test_context_budget.py:104) | Passed |
| B074 | Invalid environment values are not silently replaced with defaults. | [ContextBudgetTests.test_invalid_environment_values_are_not_silently_replaced_with_defaults](D:/personal_projects/openpoke/server/tests/test_context_budget.py:133) | Passed |
| B075 | Multilingual Unicode uses UTF-8 bytes and remains an estimate. | [ContextBudgetTests.test_multilingual_unicode_uses_utf8_bytes_and_remains_an_estimate](D:/personal_projects/openpoke/server/tests/test_context_budget.py:96) | Passed |
| B076 | Output and headroom reduce the effective input allowance. | [ContextBudgetTests.test_output_and_headroom_reduce_the_effective_input_allowance](D:/personal_projects/openpoke/server/tests/test_context_budget.py:84) | Passed |

## test_context_builder.py — 16 passed

Bounded outer-agent history/results, complete tool groups and required-context preservation.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B077 | Bounded interaction preserves full draft review and original body bytes. | [ContextBuilderTests.test_bounded_interaction_preserves_full_draft_review_and_original_body_bytes](D:/personal_projects/openpoke/server/tests/test_context_builder.py:341) | Passed |
| B078 | Read only a bounded log tail and retain complete recent request/reply episodes rather than loading the whole transcript. | [ContextBuilderTests.test_bounded_tail_keeps_recent_whole_episodes_without_full_transcript_reads](D:/personal_projects/openpoke/server/tests/test_context_builder.py:84) | Passed |
| B079 | Clear invalidates builder cached references and scope is required. | [ContextBuilderTests.test_clear_invalidates_builder_cached_references_and_scope_is_required](D:/personal_projects/openpoke/server/tests/test_context_builder.py:208) | Passed |
| B080 | A request already journaled by dispatch must not duplicate itself or displace the previous draft evidence needed by a follow-up. | [ContextBuilderTests.test_dispatch_current_request_does_not_displace_the_previous_draft_episode](D:/personal_projects/openpoke/server/tests/test_context_builder.py:99) | Passed |
| B081 | Dropped tool episodes keep complete parallel call result groups in the archive. | [ContextBuilderTests.test_dropped_tool_episodes_keep_complete_parallel_call_result_groups_in_the_archive](D:/personal_projects/openpoke/server/tests/test_context_builder.py:150) | Passed |
| B082 | Save giant current-user/callback input but reject it whole before HTTP when required instructions cannot fit; do not submit a misleading prefix. | [ContextBuilderTests.test_giant_user_and_combined_callback_are_saved_and_rejected_before_http](D:/personal_projects/openpoke/server/tests/test_context_builder.py:261) | Passed |
| B083 | Invalid or missing pairs fail even when the episode would have been omitted. | [ContextBuilderTests.test_invalid_or_missing_pairs_fail_even_when_the_episode_would_have_been_omitted](D:/personal_projects/openpoke/server/tests/test_context_builder.py:184) | Passed |
| B084 | Large results have qualified originals and exact recoverable composite snapshots. | [ContextBuilderTests.test_large_results_have_qualified_originals_and_exact_recoverable_composite_snapshots](D:/personal_projects/openpoke/server/tests/test_context_builder.py:130) | Passed |
| B085 | Reject malformed parallel tool-call groups before any tool can cause an effect. | [ContextBuilderTests.test_malformed_parallel_calls_are_rejected_before_any_tool_executes](D:/personal_projects/openpoke/server/tests/test_context_builder.py:330) | Passed |
| B086 | Missing huge or corrupt history is explicit and collision does not open another worker. | [ContextBuilderTests.test_missing_huge_or_corrupt_history_is_explicit_and_collision_does_not_open_another_worker](D:/personal_projects/openpoke/server/tests/test_context_builder.py:194) | Passed |
| B087 | If saving a preview source fails after an external tool call, stop the loop rather than replaying the already-executed action. | [ContextBuilderTests.test_preview_storage_failure_stops_after_one_external_tool_call](D:/personal_projects/openpoke/server/tests/test_context_builder.py:310) | Passed |
| B088 | Real interaction followup retains exact draft and reuses exact worker. | [ContextBuilderTests.test_real_interaction_followup_retains_exact_draft_and_reuses_exact_worker](D:/personal_projects/openpoke/server/tests/test_context_builder.py:275) | Passed |
| B089 | Run the actual worker loop with a large fake Gmail result; save its full original, preview it and recover needed source text while requests pass preflight. | [ContextBuilderTests.test_real_worker_gmail_result_is_previewed_and_recovered_under_provider_preflight](D:/personal_projects/openpoke/server/tests/test_context_builder.py:224) | Passed |
| B090 | Keep required current input, summary, latest episode and executed tool arguments exact; fail when that required floor cannot fit. | [ContextBuilderTests.test_required_input_summary_latest_history_and_exact_tool_arguments_never_get_truncated](D:/personal_projects/openpoke/server/tests/test_context_builder.py:170) | Passed |
| B091 | Summary and latest followup evidence are pinned while old history is recoverable. | [ContextBuilderTests.test_summary_and_latest_followup_evidence_are_pinned_while_old_history_is_recoverable](D:/personal_projects/openpoke/server/tests/test_context_builder.py:109) | Passed |
| B092 | Trigger style direct worker turns get request boundaries without double logging dispatch. | [ContextBuilderTests.test_trigger_style_direct_worker_turns_get_request_boundaries_without_double_logging_dispatch](D:/personal_projects/openpoke/server/tests/test_context_builder.py:367) | Passed |

## test_context_recovery.py — 18 passed

Paged source reads, selected-history search, ownership, cursors and recovery quotas.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B093 | Both runtime loops execute recovery and preserve tool pairs. | [RecoveryTests.test_both_runtime_loops_execute_recovery_and_preserve_tool_pairs](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:353) | Passed |
| B094 | Conversation selection and missing history are distinct from no matches. | [RecoveryTests.test_conversation_selection_and_missing_history_are_distinct_from_no_matches](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:219) | Passed |
| B095 | History clear and clear during a read invalidate results. | [RecoveryTests.test_history_clear_and_clear_during_a_read_invalidate_results](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:291) | Passed |
| B096 | History cursors pin source query snapshot and generation. | [RecoveryTests.test_history_cursors_pin_source_query_snapshot_and_generation](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:234) | Passed |
| B097 | Invalid arguments paths offsets and missing content fail explicitly. | [RecoveryTests.test_invalid_arguments_paths_offsets_and_missing_content_fail_explicitly](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:124) | Passed |
| B098 | JSON escaping and actual runtime wrappers are bounded. | [RecoveryTests.test_json_escaping_and_actual_runtime_wrappers_are_bounded](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:83) | Passed |
| B099 | Legacy history pages are bounded and preserve logged bytes. | [RecoveryTests.test_legacy_history_pages_are_bounded_and_preserve_logged_bytes](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:151) | Passed |
| B100 | Lookup failure and historical filename collision never guess an owner. | [RecoveryTests.test_lookup_failure_and_historical_filename_collision_never_guess_an_owner](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:263) | Passed |
| B101 | Mailbox qualification is preserved without using the active account. | [RecoveryTests.test_mailbox_qualification_is_preserved_without_using_the_active_account](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:102) | Passed |
| B102 | Owner selection is exact and cannot be overridden by a worker. | [RecoveryTests.test_owner_selection_is_exact_and_cannot_be_overridden_by_a_worker](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:114) | Passed |
| B103 | Per turn call scan and response limits stop recovery. | [RecoveryTests.test_per_turn_call_scan_and_response_limits_stop_recovery](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:272) | Passed |
| B104 | Recovery restarts without in memory cursor or reference state. | [RecoveryTests.test_recovery_restarts_without_in_memory_cursor_or_reference_state](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:306) | Passed |
| B105 | Replaced truncated and malformed history cursors fail explicitly. | [RecoveryTests.test_replaced_truncated_and_malformed_history_cursors_fail_explicitly](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:249) | Passed |
| B106 | Result paging recovers exact Unicode crlf and middle detail. | [RecoveryTests.test_result_paging_recovers_exact_unicode_crlf_and_middle_detail](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:66) | Passed |
| B107 | Runtime counters reset between turns and legacy has no recovery tools. | [RecoveryTests.test_runtime_counters_reset_between_turns_and_legacy_has_no_recovery_tools](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:389) | Passed |
| B108 | Search finds matches across chunks and scan pages. | [RecoveryTests.test_search_finds_matches_across_chunks_and_scan_pages](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:202) | Passed |
| B109 | Selected history search streams one file and distinguishes partial scan. | [RecoveryTests.test_selected_history_search_streams_one_file_and_distinguishes_partial_scan](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:169) | Passed |
| B110 | Tools are executable only with a backend owned scope and budget. | [RecoveryTests.test_tools_are_executable_only_with_a_backend_owned_scope_and_budget](D:/personal_projects/openpoke/server/tests/test_context_recovery.py:337) | Passed |

## test_data_paths.py — 5 passed

Configured data-root resolution, persistence and scoped clearing.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B111 | Default matches legacy data directory. | [DataPathTests.test_default_matches_legacy_data_directory](D:/personal_projects/openpoke/server/tests/test_data_paths.py:92) | Passed |
| B112 | Empty environment override is rejected. | [DataPathTests.test_empty_environment_override_is_rejected](D:/personal_projects/openpoke/server/tests/test_data_paths.py:114) | Passed |
| B113 | Environment override is resolved without creating directory. | [DataPathTests.test_environment_override_is_resolved_without_creating_directory](D:/personal_projects/openpoke/server/tests/test_data_paths.py:99) | Passed |
| B114 | Relative and home paths are expanded. | [DataPathTests.test_relative_and_home_paths_are_expanded](D:/personal_projects/openpoke/server/tests/test_data_paths.py:108) | Passed |
| B115 | Stores persist after restart and clear only their configured root. | [DataPathTests.test_stores_persist_after_restart_and_clear_only_their_configured_root](D:/personal_projects/openpoke/server/tests/test_data_paths.py:134) | Passed |

## test_default_strategies.py — 7 passed

Fresh-process bounded defaults, allowances and independent legacy opt-outs.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B116 | Custom models require allowances for each selected component. | [DefaultStrategySettingsTests.test_custom_models_require_allowances_for_each_selected_component](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:143) | Passed |
| B117 | Defaults use bounded strategies and an independent bundled policy. | [DefaultStrategySettingsTests.test_defaults_use_bounded_strategies_and_an_independent_bundled_policy](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:136) | Passed |
| B118 | Explicit legacy choices remain independent and constructor values win. | [DefaultStrategySettingsTests.test_explicit_legacy_choices_remain_independent_and_constructor_values_win](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:152) | Passed |
| B119 | Invalid or explicit empty configuration never uses a fallback. | [DefaultStrategySettingsTests.test_invalid_or_explicit_empty_configuration_never_uses_a_fallback](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:161) | Passed |
| B120 | Fresh defaults enable lookup recovery and provider preflight. | [DefaultStrategyStartupTests.test_fresh_defaults_enable_lookup_recovery_and_provider_preflight](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:190) | Passed |
| B121 | Restart opt out and reenable preserve existing files and references. | [DefaultStrategyStartupTests.test_restart_opt_out_and_reenable_preserve_existing_files_and_references](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:210) | Passed |
| B122 | Unknown model startup fails before creating stores until configured. | [DefaultStrategyStartupTests.test_unknown_model_startup_fails_before_creating_stores_until_configured](D:/personal_projects/openpoke/server/tests/test_default_strategies.py:202) | Passed |

## test_discovery_quality.py — 12 passed

Discovery-v2 frozen data, disjoint families, real rankers, metrics and family-cluster accounting.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B123 | Catalogs are nested and three draws have different backgrounds. | [DiscoveryDatasetTests.test_catalogs_are_nested_and_three_draws_have_different_backgrounds](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:71) | Passed |
| B124 | Corrupted source is rejected instead of refreezing. | [DiscoveryDatasetTests.test_corrupted_source_is_rejected_instead_of_refreezing](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:41) | Passed |
| B125 | Verify the discovery-v2 dormant targets are genuinely excluded from the rendered recent roster, so their retrieval scenarios cannot be satisfied by recent-list visibility alone. | [DiscoveryDatasetTests.test_dormant_targets_really_are_outside_the_recent_roster](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:93) | Passed |
| B126 | Verify all 100 discovery-v2 workers are judged targets and whole families stay in either development or evaluation. | [DiscoveryDatasetTests.test_frozen_families_cover_every_owner_with_disjoint_splits](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:32) | Passed |
| B127 | Build larger catalogs and public search projections without consulting query text, judgments or hidden owner labels. | [DiscoveryDatasetTests.test_generation_and_search_projection_do_not_consume_queries_or_gold](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:84) | Passed |
| B128 | Invalid labels cross family splits and oversized metadata are rejected. | [DiscoveryDatasetTests.test_invalid_labels_cross_family_splits_and_oversized_metadata_are_rejected](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:52) | Passed |
| B129 | All owner coverage precision and packing have distinct meanings. | [DiscoveryMetricTests.test_all_owner_coverage_precision_and_packing_have_distinct_meanings](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:106) | Passed |
| B130 | Average background draws within a request before family-cluster intervals; failed draw coverage excludes the whole affected request. | [DiscoveryMetricTests.test_draws_collapse_before_family_intervals_and_failures_exclude_whole_requests](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:125) | Passed |
| B131 | Exclude insufficient-metadata diagnostic requests from primary quality metrics and keep no-match requests out of owner-recall denominators. | [DiscoveryMetricTests.test_missing_evidence_and_no_match_do_not_inflate_recall_denominators](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:116) | Passed |
| B132 | Paired comparison uses matching requests and family clusters. | [DiscoveryMetricTests.test_paired_comparison_uses_matching_requests_and_family_clusters](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:136) | Passed |
| B133 | CLI runs real rankers preserves inputs hashes and existing destinations. | [DiscoveryQualityCliTests.test_cli_runs_real_rankers_preserves_inputs_hashes_and_existing_destinations](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:157) | Passed |
| B134 | Live agent empty catalog and duplicate draw controls fail before output. | [DiscoveryQualityCliTests.test_live_agent_empty_catalog_and_duplicate_draw_controls_fail_before_output](D:/personal_projects/openpoke/server/tests/test_discovery_quality.py:180) | Passed |

## test_draft_references.py — 23 passed

Exact draft/body references, full review, identifiers, ownership, integrity and sending.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B135 | Body pointer missing ambiguous or non string is an explicit limitation. | [DraftReferenceTests.test_body_pointer_missing_ambiguous_or_non_string_is_an_explicit_limitation](D:/personal_projects/openpoke/server/tests/test_draft_references.py:205) | Passed |
| B136 | Clear invalidates old drafts and body refs without resolving replacement history. | [DraftReferenceTests.test_clear_invalidates_old_drafts_and_body_refs_without_resolving_replacement_history](D:/personal_projects/openpoke/server/tests/test_draft_references.py:271) | Passed |
| B137 | Create from JSON reference preserves complete body and all recipient options. | [DraftReferenceTests.test_create_from_json_reference_preserves_complete_body_and_all_recipient_options](D:/personal_projects/openpoke/server/tests/test_draft_references.py:85) | Passed |
| B138 | Draft refs survive a network blocked fresh process restart. | [DraftReferenceTests.test_draft_refs_survive_a_network_blocked_fresh_process_restart](D:/personal_projects/openpoke/server/tests/test_draft_references.py:286) | Passed |
| B139 | Empty body and backend read limits are exact and never silently truncate. | [DraftReferenceTests.test_empty_body_and_backend_read_limits_are_exact_and_never_silently_truncate](D:/personal_projects/openpoke/server/tests/test_draft_references.py:234) | Passed |
| B140 | Full review and bounded history keep exact draft refs for small and giant bodies. | [DraftReferenceTests.test_full_review_and_bounded_history_keep_exact_draft_refs_for_small_and_giant_bodies](D:/personal_projects/openpoke/server/tests/test_draft_references.py:105) | Passed |
| B141 | Inline overrides cannot change a referenced draft or its recipients. | [DraftReferenceTests.test_inline_overrides_cannot_change_a_referenced_draft_or_its_recipients](D:/personal_projects/openpoke/server/tests/test_draft_references.py:130) | Passed |
| B142 | Run both scripted agents through large referenced draft creation, full review, a separate confirmation and exact original fake send. | [DraftReferenceTests.test_large_draft_two_agent_review_confirmation_and_send_stay_bounded_and_exact](D:/personal_projects/openpoke/server/tests/test_draft_references.py:445) | Passed |
| B143 | Mailbox change does not rebind body or draft references. | [DraftReferenceTests.test_mailbox_change_does_not_rebind_body_or_draft_references](D:/personal_projects/openpoke/server/tests/test_draft_references.py:158) | Passed |
| B144 | Manifest body qualification and digest cannot point to another source. | [DraftReferenceTests.test_manifest_body_qualification_and_digest_cannot_point_to_another_source](D:/personal_projects/openpoke/server/tests/test_draft_references.py:243) | Passed |
| B145 | Missing truncated and changed same size bodies fail before effects or review. | [DraftReferenceTests.test_missing_truncated_and_changed_same_size_bodies_fail_before_effects_or_review](D:/personal_projects/openpoke/server/tests/test_draft_references.py:185) | Passed |
| B146 | Other worker and forged owner selectors never resolve the original. | [DraftReferenceTests.test_other_worker_and_forged_owner_selectors_never_resolve_the_original](D:/personal_projects/openpoke/server/tests/test_draft_references.py:144) | Passed |
| B147 | Post create reference failure stops worker without replaying external action. | [DraftReferenceTests.test_post_create_reference_failure_stops_worker_without_replaying_external_action](D:/personal_projects/openpoke/server/tests/test_draft_references.py:415) | Passed |
| B148 | Post review marker failure does not repeat the full visible review. | [DraftReferenceTests.test_post_review_marker_failure_does_not_repeat_the_full_visible_review](D:/personal_projects/openpoke/server/tests/test_draft_references.py:434) | Passed |
| B149 | Reject a Gmail draft ID incorrectly placed in a c1_ saved-reference selector before source or Gmail IO. | [DraftReferenceTests.test_provider_id_in_a_draft_selector_is_an_argument_error_without_source_or_gmail_io](D:/personal_projects/openpoke/server/tests/test_draft_references.py:328) | Passed |
| B150 | Provider missing draft id is explicit and never guessed for sending. | [DraftReferenceTests.test_provider_missing_draft_id_is_explicit_and_never_guessed_for_sending](D:/personal_projects/openpoke/server/tests/test_draft_references.py:390) | Passed |
| B151 | Reply and forward resolve exact referenced text without changing recipients. | [DraftReferenceTests.test_reply_and_forward_resolve_exact_referenced_text_without_changing_recipients](D:/personal_projects/openpoke/server/tests/test_draft_references.py:378) | Passed |
| B152 | Review marker binding is checked instead of hiding a different visible draft. | [DraftReferenceTests.test_review_marker_binding_is_checked_instead_of_hiding_a_different_visible_draft](D:/personal_projects/openpoke/server/tests/test_draft_references.py:255) | Passed |
| B153 | Review markers preserve exact worker names and remain readable in legacy mode. | [DraftReferenceTests.test_review_markers_preserve_exact_worker_names_and_remain_readable_in_legacy_mode](D:/personal_projects/openpoke/server/tests/test_draft_references.py:399) | Passed |
| B154 | Send a reviewed provider draft ID through draft_id directly; do not try to resolve it as saved content. | [DraftReferenceTests.test_reviewed_provider_id_sends_directly_without_saved_source_resolution](D:/personal_projects/openpoke/server/tests/test_draft_references.py:372) | Passed |
| B155 | Schema changes are bounded only and have existing executable handlers. | [DraftReferenceTests.test_schema_changes_are_bounded_only_and_have_existing_executable_handlers](D:/personal_projects/openpoke/server/tests/test_draft_references.py:310) | Passed |
| B156 | Unknown mailbox draft can be reviewed but cannot be sent by reference. | [DraftReferenceTests.test_unknown_mailbox_draft_can_be_reviewed_but_cannot_be_sent_by_reference](D:/personal_projects/openpoke/server/tests/test_draft_references.py:171) | Passed |
| B157 | After an invalid saved selector, allow a separate corrected provider-ID call and produce exactly one original send without recreation. | [DraftReferenceTests.test_wrong_saved_selector_can_be_corrected_by_an_explicit_provider_id_call](D:/personal_projects/openpoke/server/tests/test_draft_references.py:375) | Passed |

## test_fake_gmail.py — 14 passed

Stateful fake-provider semantics through actual adapters, including uncertain writes.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B158 | Inject provider failure before a fake send and after a fake send; preserve the difference between no effect and an effect whose response was lost. | [FakeGmailTests.test_before_and_after_failure_expose_the_actual_send_outcome](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:105) | Passed |
| B159 | Create then send preserves exact body recipients and attachments. | [FakeGmailTests.test_create_then_send_preserves_exact_body_recipients_and_attachments](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:62) | Passed |
| B160 | Delete removes a draft without sending. | [FakeGmailTests.test_delete_removes_a_draft_without_sending](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:135) | Passed |
| B161 | Duplicate ids in two accounts never cross mailbox boundaries. | [FakeGmailTests.test_duplicate_ids_in_two_accounts_never_cross_mailbox_boundaries](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:87) | Passed |
| B162 | Email search and runtime distinguish failure from empty success. | [FakeGmailTests.test_email_search_and_runtime_distinguish_failure_from_empty_success](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:190) | Passed |
| B163 | Fake session restores the connection binding. | [FakeGmailTests.test_fake_session_restores_the_connection_binding](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:229) | Passed |
| B164 | Fixed clock controls recency without wall clock time. | [FakeGmailTests.test_fixed_clock_controls_recency_without_wall_clock_time](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:166) | Passed |
| B165 | Forward retains source text and records the new thread. | [FakeGmailTests.test_forward_retains_source_text_and_records_the_new_thread](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:143) | Passed |
| B166 | Pagination is stable and bound to account and query. | [FakeGmailTests.test_pagination_is_stable_and_bound_to_account_and_query](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:47) | Passed |
| B167 | People search and people paging use current argument names. | [FakeGmailTests.test_people_search_and_people_paging_use_current_argument_names](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:155) | Passed |
| B168 | Replaying the same operations reproduces ids and evidence. | [FakeGmailTests.test_replaying_the_same_operations_reproduces_ids_and_evidence](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:175) | Passed |
| B169 | Demonstrate that blindly retrying an uncertain reply can duplicate the effect; the fake does not invent exactly-once behavior. | [FakeGmailTests.test_reply_retry_can_produce_a_duplicate_after_an_uncertain_result](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:125) | Passed |
| B170 | Search uses real adapters parser and exact provider ids. | [FakeGmailTests.test_search_uses_real_adapters_parser_and_exact_provider_ids](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:32) | Passed |
| B171 | Unsupported operations and unknown accounts fail without fallback. | [FakeGmailTests.test_unsupported_operations_and_unknown_accounts_fail_without_fallback](D:/personal_projects/openpoke/server/tests/test_fake_gmail.py:214) | Passed |

## test_gmail_connection.py — 9 passed

Mocked SDK connection/status/disconnect and saved routing identity.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B172 | Account response shapes. | [GmailConnectionTests.test_account_response_shapes](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:103) | Passed |
| B173 | Connection owner is used instead of stale browser user. | [GmailConnectionTests.test_connection_owner_is_used_instead_of_stale_browser_user](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:46) | Passed |
| B174 | Disconnect lists items and clears saved user. | [GmailConnectionTests.test_disconnect_lists_items_and_clears_saved_user](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:81) | Passed |
| B175 | Failed composio result raises instead of becoming empty mailbox. | [GmailConnectionTests.test_failed_composio_result_raises_instead_of_becoming_empty_mailbox](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:112) | Passed |
| B176 | Failed disconnect keeps saved connection. | [GmailConnectionTests.test_failed_disconnect_keeps_saved_connection](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:92) | Passed |
| B177 | Pending oauth does not activate user. | [GmailConnectionTests.test_pending_oauth_does_not_activate_user](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:56) | Passed |
| B178 | Status finds SDK items and restores user after restart. | [GmailConnectionTests.test_status_finds_sdk_items_and_restores_user_after_restart](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:34) | Passed |
| B179 | Status service error preserves saved connection. | [GmailConnectionTests.test_status_service_error_preserves_saved_connection](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:73) | Passed |
| B180 | Unconnected status clears saved user. | [GmailConnectionTests.test_unconnected_status_clears_saved_user](D:/personal_projects/openpoke/server/tests/test_gmail_connection.py:65) | Passed |

## test_gmail_tool_errors.py — 3 passed

Distinguishing provider errors from successful empty results.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B181 | Empty search result is successful. | [GmailToolErrorTests.test_empty_search_result_is_successful](D:/personal_projects/openpoke/server/tests/test_gmail_tool_errors.py:16) | Passed |
| B182 | Execution tool recognizes error payload. | [GmailToolErrorTests.test_execution_tool_recognizes_error_payload](D:/personal_projects/openpoke/server/tests/test_gmail_tool_errors.py:9) | Passed |
| B183 | Internal fetch passes keyword only arguments. | [GmailToolErrorTests.test_internal_fetch_passes_keyword_only_arguments](D:/personal_projects/openpoke/server/tests/test_gmail_tool_errors.py:23) | Passed |

## test_inner_context.py — 27 passed

Bounded search, classification, watcher retry and resumable summarization.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B184 | Classifier can recover a middle detail without overflowing. | [InnerContextTests.test_classifier_can_recover_a_middle_detail_without_overflowing](D:/personal_projects/openpoke/server/tests/test_inner_context.py:218) | Passed |
| B185 | Classifier checks original source qualification before model work. | [InnerContextTests.test_classifier_checks_original_source_qualification_before_model_work](D:/personal_projects/openpoke/server/tests/test_inner_context.py:388) | Passed |
| B186 | A classifier that has not covered the entire cleaned body cannot declare the email unimportant; return unavailable instead. | [InnerContextTests.test_classifier_incomplete_body_is_unavailable_instead_of_a_negative_decision](D:/personal_projects/openpoke/server/tests/test_inner_context.py:252) | Passed |
| B187 | Classifier rejects an oversized notification without truncating it. | [InnerContextTests.test_classifier_rejects_an_oversized_notification_without_truncating_it](D:/personal_projects/openpoke/server/tests/test_inner_context.py:238) | Passed |
| B188 | Classifier required headers and unsupported decisions fail without guesses. | [InnerContextTests.test_classifier_required_headers_and_unsupported_decisions_fail_without_guesses](D:/personal_projects/openpoke/server/tests/test_inner_context.py:263) | Passed |
| B189 | Default summary settings use a bounded effective window. | [InnerContextTests.test_default_summary_settings_use_a_bounded_effective_window](D:/personal_projects/openpoke/server/tests/test_inner_context.py:449) | Passed |
| B190 | Legacy memory loading does not inherit bounded header limits. | [InnerContextTests.test_legacy_memory_loading_does_not_inherit_bounded_header_limits](D:/personal_projects/openpoke/server/tests/test_inner_context.py:466) | Passed |
| B191 | Legacy summary index adoption is bounded then writes a resume cursor. | [InnerContextTests.test_legacy_summary_index_adoption_is_bounded_then_writes_a_resume_cursor](D:/personal_projects/openpoke/server/tests/test_inner_context.py:395) | Passed |
| B192 | Search cache and query caps stop more SDK work with sources preserved. | [InnerContextTests.test_search_cache_and_query_caps_stop_more_sdk_work_with_sources_preserved](D:/personal_projects/openpoke/server/tests/test_inner_context.py:177) | Passed |
| B193 | An SDK/search failure cannot be reported as a successful lookup with zero messages. | [InnerContextTests.test_search_failure_cannot_complete_as_an_empty_lookup](D:/personal_projects/openpoke/server/tests/test_inner_context.py:153) | Passed |
| B194 | Continue all search pages against the original executed mailbox even when the currently active account changes. | [InnerContextTests.test_search_pagination_stays_with_the_executed_account_after_active_account_changes](D:/personal_projects/openpoke/server/tests/test_inner_context.py:363) | Passed |
| B195 | Search parent hints are bounded with a complete qualified index. | [InnerContextTests.test_search_parent_hints_are_bounded_with_a_complete_qualified_index](D:/personal_projects/openpoke/server/tests/test_inner_context.py:131) | Passed |
| B196 | Search previews large email and recovers middle fact under real preflight. | [InnerContextTests.test_search_previews_large_email_and_recovers_middle_fact_under_real_preflight](D:/personal_projects/openpoke/server/tests/test_inner_context.py:96) | Passed |
| B197 | Search successful empty lookup can complete and unknown ids cannot. | [InnerContextTests.test_search_successful_empty_lookup_can_complete_and_unknown_ids_cannot](D:/personal_projects/openpoke/server/tests/test_inner_context.py:166) | Passed |
| B198 | Source and retained message budgets do not discard the original. | [InnerContextTests.test_source_and_retained_message_budgets_do_not_discard_the_original](D:/personal_projects/openpoke/server/tests/test_inner_context.py:197) | Passed |
| B199 | Source recovery rejects foreign refs exhaustion and old cached writes. | [InnerContextTests.test_source_recovery_rejects_foreign_refs_exhaustion_and_old_cached_writes](D:/personal_projects/openpoke/server/tests/test_inner_context.py:565) | Passed |
| B200 | Reject a stale summarizer commit after a concurrent summary change or conversation replacement. | [InnerContextTests.test_summary_cas_and_replaced_conversation_cannot_adopt_stale_state](D:/personal_projects/openpoke/server/tests/test_inner_context.py:548) | Passed |
| B201 | Summary existing source refs have executable bounded reads and are retained. | [InnerContextTests.test_summary_existing_source_refs_have_executable_bounded_reads_and_are_retained](D:/personal_projects/openpoke/server/tests/test_inner_context.py:416) | Passed |
| B202 | Summary keeps the existing two attempt limit for transient failure. | [InnerContextTests.test_summary_keeps_the_existing_two_attempt_limit_for_transient_failure](D:/personal_projects/openpoke/server/tests/test_inner_context.py:434) | Passed |
| B203 | Summary read budget source limits and stale generation do not commit. | [InnerContextTests.test_summary_read_budget_source_limits_and_stale_generation_do_not_commit](D:/personal_projects/openpoke/server/tests/test_inner_context.py:524) | Passed |
| B204 | Summary required user input and generated output limits preserve old progress. | [InnerContextTests.test_summary_required_user_input_and_generated_output_limits_preserve_old_progress](D:/personal_projects/openpoke/server/tests/test_inner_context.py:511) | Passed |
| B205 | Summary resumes at committed offset and legacy can recover the pending tail. | [InnerContextTests.test_summary_resumes_at_committed_offset_and_legacy_can_recover_the_pending_tail](D:/personal_projects/openpoke/server/tests/test_inner_context.py:330) | Passed |
| B206 | Summary saves large informational entries and recovers middle details. | [InnerContextTests.test_summary_saves_large_informational_entries_and_recovers_middle_details](D:/personal_projects/openpoke/server/tests/test_inner_context.py:488) | Passed |
| B207 | Shrink a summary batch by complete entries to fit; commit the cursor only through processed entries and leave the remaining tail available. | [InnerContextTests.test_summary_shrinks_complete_batches_and_never_advances_past_input_it_did_not_process](D:/personal_projects/openpoke/server/tests/test_inner_context.py:473) | Passed |
| B208 | Watcher clear or failed lookup cannot emit or commit an old notification. | [InnerContextTests.test_watcher_clear_or_failed_lookup_cannot_emit_or_commit_an_old_notification](D:/personal_projects/openpoke/server/tests/test_inner_context.py:314) | Passed |
| B209 | Keep an incompletely classified email unseen and eligible for retry beyond the next age cutoff while it remains in the fetched window. | [InnerContextTests.test_watcher_does_not_mark_an_incomplete_classification_seen_and_retries_past_age_cutoff](D:/personal_projects/openpoke/server/tests/test_inner_context.py:279) | Passed |
| B210 | Watcher seen ids are qualified and notifications keep the fetched account. | [InnerContextTests.test_watcher_seen_ids_are_qualified_and_notifications_keep_the_fetched_account](D:/personal_projects/openpoke/server/tests/test_inner_context.py:297) | Passed |

## test_observability.py — 10 passed

Asynchronous correlation, concurrency, callbacks, triggers, polling and completion outcomes.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B211 | Chat trace reaches worker tool callback and user reply. | [AgentTraceTests.test_chat_trace_reaches_worker_tool_callback_and_user_reply](D:/personal_projects/openpoke/server/tests/test_observability.py:165) | Passed |
| B212 | Execution cancellation is measured and propagates. | [AgentTraceTests.test_execution_cancellation_is_measured_and_propagates](D:/personal_projects/openpoke/server/tests/test_observability.py:312) | Passed |
| B213 | Execution timeout is measured without changing the result. | [AgentTraceTests.test_execution_timeout_is_measured_without_changing_the_result](D:/personal_projects/openpoke/server/tests/test_observability.py:298) | Passed |
| B214 | Gmail poll links classification to notification. | [AgentTraceTests.test_gmail_poll_links_classification_to_notification](D:/personal_projects/openpoke/server/tests/test_observability.py:216) | Passed |
| B215 | Mixed request batch links every parent without changing the callback. | [AgentTraceTests.test_mixed_request_batch_links_every_parent_without_changing_the_callback](D:/personal_projects/openpoke/server/tests/test_observability.py:261) | Passed |
| B216 | Search and summary calls label their component and keep the parent. | [AgentTraceTests.test_search_and_summary_calls_label_their_component_and_keep_the_parent](D:/personal_projects/openpoke/server/tests/test_observability.py:244) | Passed |
| B217 | Trigger state update failure records one failed completion. | [AgentTraceTests.test_trigger_state_update_failure_records_one_failed_completion](D:/personal_projects/openpoke/server/tests/test_observability.py:335) | Passed |
| B218 | Trigger trace survives worker and async callback. | [AgentTraceTests.test_trigger_trace_survives_worker_and_async_callback](D:/personal_projects/openpoke/server/tests/test_observability.py:197) | Passed |
| B219 | Child turn and exception restore the parent and filter content fields. | [TraceContextTests.test_child_turn_and_exception_restore_the_parent_and_filter_content_fields](D:/personal_projects/openpoke/server/tests/test_observability.py:58) | Passed |
| B220 | Concurrent requests keep independent ids and restore context. | [TraceContextTests.test_concurrent_requests_keep_independent_ids_and_restore_context](D:/personal_projects/openpoke/server/tests/test_observability.py:38) | Passed |

## test_observation_evidence.py — 3 passed

Availability/provenance states, missing values and derivation evidence.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B221 | All four states and provenance survive JSON serialization. | [ObservationEvidenceTests.test_all_four_states_and_provenance_survive_json_serialization](D:/personal_projects/openpoke/server/tests/test_observation_evidence.py:14) | Passed |
| B222 | Dangling evidence is not emitted and an unknown failure is not inapplicable. | [ObservationEvidenceTests.test_dangling_evidence_is_not_emitted_and_an_unknown_failure_is_not_inapplicable](D:/personal_projects/openpoke/server/tests/test_observation_evidence.py:66) | Passed |
| B223 | Invalid states reasons and unsupported inferences are rejected. | [ObservationEvidenceTests.test_invalid_states_reasons_and_unsupported_inferences_are_rejected](D:/personal_projects/openpoke/server/tests/test_observation_evidence.py:47) | Passed |

## test_openrouter_client.py — 15 passed

Provider boundary, mock scope, usage, error categories, cancellation and logging isolation.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B224 | Cancellation is measured once and propagates. | [OpenRouterClientTests.test_cancellation_is_measured_once_and_propagates](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:281) | Passed |
| B225 | Error envelope is measured and returned unchanged. | [OpenRouterClientTests.test_error_envelope_is_measured_and_returned_unchanged](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:269) | Passed |
| B226 | Failed provider call can still have available usage. | [OpenRouterClientTests.test_failed_provider_call_can_still_have_available_usage](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:128) | Passed |
| B227 | HTTP failures have safe categories. | [OpenRouterClientTests.test_http_failures_have_safe_categories](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:207) | Passed |
| B228 | Log sink failure does not change success or mask provider errors. | [OpenRouterClientTests.test_log_sink_failure_does_not_change_success_or_mask_provider_errors](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:302) | Passed |
| B229 | Missing and invalid usage are unknown and zero is preserved. | [OpenRouterClientTests.test_missing_and_invalid_usage_are_unknown_and_zero_is_preserved](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:77) | Passed |
| B230 | Missing key is measured without HTTP request. | [OpenRouterClientTests.test_missing_key_is_measured_without_http_request](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:253) | Passed |
| B231 | Missing usage reasons are specific and safe. | [OpenRouterClientTests.test_missing_usage_reasons_are_specific_and_safe](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:106) | Passed |
| B232 | Mock binding survives scope exit in a spawned task. | [OpenRouterClientTests.test_mock_binding_survives_scope_exit_in_a_spawned_task](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:167) | Passed |
| B233 | Mock failure never constructs a live client and requires mock transport. | [OpenRouterClientTests.test_mock_failure_never_constructs_a_live_client_and_requires_mock_transport](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:184) | Passed |
| B234 | Nested mock scopes restore the transport and live default. | [OpenRouterClientTests.test_nested_mock_scopes_restore_the_transport_and_live_default](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:143) | Passed |
| B235 | Provider error keeps message without metadata dump. | [OpenRouterClientTests.test_provider_error_keeps_message_without_metadata_dump](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:336) | Passed |
| B236 | Request includes configured output limit. | [OpenRouterClientTests.test_request_includes_configured_output_limit](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:318) | Passed |
| B237 | Transport and decoding failures are measured. | [OpenRouterClientTests.test_transport_and_decoding_failures_are_measured](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:227) | Passed |
| B238 | Usage and timing preserve payload and exclude content. | [OpenRouterClientTests.test_usage_and_timing_preserve_payload_and_exclude_content](D:/personal_projects/openpoke/server/tests/test_openrouter_client.py:28) | Passed |

## test_worker_discovery.py — 20 passed

Recent roster, whole-catalog lookup, exact identity, metadata and creation guards.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B239 | Chat and callback use bounded prompts with current request. | [WorkerDiscoveryRuntimeTests.test_chat_and_callback_use_bounded_prompts_with_current_request](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:302) | Passed |
| B240 | Dispatch an exact existing name directly and retain its original worker journal; no lookup is required for exact reuse. | [WorkerDiscoveryRuntimeTests.test_existing_exact_name_reuses_original_history_without_lookup](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:277) | Passed |
| B241 | A failed lookup following an earlier success revokes discovery permission and blocks a new worker. | [WorkerDiscoveryRuntimeTests.test_failed_lookup_revokes_previous_success_and_cannot_create](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:252) | Passed |
| B242 | An empty roster permits creation of its first worker without a prior discovery call. | [WorkerDiscoveryRuntimeTests.test_first_worker_can_be_created_without_prior_lookup](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:287) | Passed |
| B243 | Full formatted lookup response is bounded for large arguments. | [WorkerDiscoveryRuntimeTests.test_full_formatted_lookup_response_is_bounded_for_large_arguments](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:294) | Passed |
| B244 | Reject invalid lookup arguments and model-invented discovery authorization rather than admitting new work. | [WorkerDiscoveryRuntimeTests.test_invalid_lookup_arguments_and_forged_state_cannot_authorize_creation](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:264) | Passed |
| B245 | Real batch dispatch updates metadata without changing exact name. | [WorkerDiscoveryRuntimeTests.test_real_batch_dispatch_updates_metadata_without_changing_exact_name](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:317) | Passed |
| B246 | Permit creation after successful discovery only within that Interaction Agent loop; a later loop cannot inherit the permission. | [WorkerDiscoveryRuntimeTests.test_successful_lookup_allows_creation_only_in_its_own_loop](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:234) | Passed |
| B247 | Update short purpose/recent-assignment metadata as work starts; preserve authoritative roster/history and verify persistence and rebuild behavior. | [WorkerDiscoveryTests.test_assignment_metadata_is_incremental_persistent_and_rebuildable](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:75) | Passed |
| B248 | Atomic write failure keeps original roster. | [WorkerDiscoveryTests.test_atomic_write_failure_keeps_original_roster](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:135) | Passed |
| B249 | At 100, 1,000 and 10,000 workers, verify bounded recent/lookup output, first-ranked exact-name retrieval and no worker-history scan. | [WorkerDiscoveryTests.test_catalogs_obey_roster_and_lookup_budgets_without_log_scans](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:33) | Passed |
| B250 | Clamps query and count and rejects invalid queries. | [WorkerDiscoveryTests.test_clamps_query_and_count_and_rejects_invalid_queries](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:160) | Passed |
| B251 | Clear route removes sidecar and late assignment does not restore it. | [WorkerDiscoveryTests.test_clear_route_removes_sidecar_and_late_assignment_does_not_restore_it](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:176) | Passed |
| B252 | Concurrent membership and collision checks use fresh state. | [WorkerDiscoveryTests.test_concurrent_membership_and_collision_checks_use_fresh_state](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:121) | Passed |
| B253 | Historical collisions are reported and new collisions rejected. | [WorkerDiscoveryTests.test_historical_collisions_are_reported_and_new_collisions_rejected](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:107) | Passed |
| B254 | Invalid roster or metadata is explicit not empty results. | [WorkerDiscoveryTests.test_invalid_roster_or_metadata_is_explicit_not_empty_results](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:145) | Passed |
| B255 | Keep Alice lunch and Alice contract as distinct exact identities, including case/Unicode/whitespace variants; lookup must not merge their histories. | [WorkerDiscoveryTests.test_names_are_exact_and_alice_topics_stay_separate](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:65) | Passed |
| B256 | Register a dormant worker and six active workers; confirm the dormant worker is absent from the recent list but returned first by the real backend lookup. This does not test the model deciding to call the tool. | [WorkerDiscoveryTests.test_old_worker_is_findable_outside_recent_entries](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:54) | Passed |
| B257 | Strategy is validated and legacy prompt and tools remain available. | [WorkerDiscoveryTests.test_strategy_is_validated_and_legacy_prompt_and_tools_remain_available](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:190) | Passed |
| B258 | Unknown activity is labelled and giant names do not break budget. | [WorkerDiscoveryTests.test_unknown_activity_is_labelled_and_giant_names_do_not_break_budget](D:/personal_projects/openpoke/server/tests/test_worker_discovery.py:94) | Passed |

## test_worker_ranking.py — 14 passed

Heuristic/IDF/BM25 compatibility, selection, failures and evaluation integration.

| Case | Scenario exercised | Exact test | Result |
| --- | --- | --- | --- |
| B259 | An actual ranker error must become failed discovery, revoke prior success and prevent new-worker creation. | [WorkerRankingAgentTests.test_ranker_failure_revokes_discovery_and_cannot_create_a_worker](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:160) | Passed |
| B260 | Script the Interaction Agent to call find_worker for each configured ranker, verify its returned tool data against real lookup, and check preflight on every model request. Tool choice is scripted. | [WorkerRankingAgentTests.test_real_lookup_loop_uses_selected_ranker_with_bounded_preflight](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:177) | Passed |
| B261 | Fixed agent comparison keeps strategies effects and model controls. | [WorkerRankingCliTests.test_fixed_agent_comparison_keeps_strategies_effects_and_model_controls](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:249) | Passed |
| B262 | Invalid controls and live without agent mode do not create evidence. | [WorkerRankingCliTests.test_invalid_controls_and_live_without_agent_mode_do_not_create_evidence](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:267) | Passed |
| B263 | Offline comparison saves real rankings separate labels and artifact hashes. | [WorkerRankingCliTests.test_offline_comparison_saves_real_rankings_separate_labels_and_artifact_hashes](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:226) | Passed |
| B264 | Bm25 saturates frequency and normalizes field length. | [WorkerRankingTests.test_bm25_saturates_frequency_and_normalizes_field_length](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:94) | Passed |
| B265 | Catalog is detached immutable and never contains fixture gold. | [WorkerRankingTests.test_catalog_is_detached_immutable_and_never_contains_fixture_gold](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:66) | Passed |
| B266 | Exact names Unicode ties and missing metadata in every method. | [WorkerRankingTests.test_exact_names_unicode_ties_and_missing_metadata_in_every_method](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:52) | Passed |
| B267 | Heuristic matches frozen pre refactor responses. | [WorkerRankingTests.test_heuristic_matches_frozen_pre_refactor_responses](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:41) | Passed |
| B268 | Idf prefers distinctive topics and rewards coverage. | [WorkerRankingTests.test_idf_prefers_distinctive_topics_and_rewards_coverage](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:80) | Passed |
| B269 | Injected ranker contract failures are not empty successes. | [WorkerRankingTests.test_injected_ranker_contract_failures_are_not_empty_successes](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:104) | Passed |
| B270 | Lookup limits collisions metadata updates and clear for all rankers. | [WorkerRankingTests.test_lookup_limits_collisions_metadata_updates_and_clear_for_all_rankers](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:118) | Passed |
| B271 | Retrieval metrics distinguish ambiguity packing and no match cases. | [WorkerRankingTests.test_retrieval_metrics_distinguish_ambiguity_packing_and_no_match_cases](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:149) | Passed |
| B272 | Setting selection is validated independent and constructor wins. | [WorkerRankingTests.test_setting_selection_is_validated_independent_and_constructor_wins](D:/personal_projects/openpoke/server/tests/test_worker_ranking.py:133) | Passed |

## Frontend checks

| Case | Scenario exercised | Result |
| --- | --- | --- |
| F01 | parsed history preserves literal escapes, actual controls and whitespace | Passed |
| F02 | a large reviewed body survives JSON, history conversion and the actual chat component | Passed |
| F03 | invalid or empty history entries are ignored without altering valid entries | Passed |
| F04 | the chat proxy preserves content and asynchronous acceptance | Passed |
| F05 | the history proxy returns the complete review and forwards clearing | Passed |

Evidence: [backend log](checks/backend.log), [frontend log](checks/frontend.log), [machine-readable map and test-source hashes](test-cases.json).
