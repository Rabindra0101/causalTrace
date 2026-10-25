# Demonstration script - target 2 minutes 40 seconds

Record the real running application. Disclose any cuts in waiting time. Keep the
public YouTube video below three minutes and never show tokens or environment files.

| Time | Screen and narration |
| --- | --- |
| 0:00-0:20 | Dashboard: an update can break imports, APIs or configuration. We need evidence for when behavior changed and whether a repair works. |
| 0:20-0:40 | Select Broken package import and Find the breaking change. Explain the labeled synthetic history, isolated Docker tests and opt-in evidence sharing. |
| 0:40-1:10 | Run with live Nebius inference. Show the actual collection failure, first failing commit and passing parent. Show the unrelated latest commit does not fix the failure when reversed. |
| 1:10-1:45 | Show NVIDIA Nemotron's explanation from Nebius Token Factory, source proposal and independently measured unchanged-suite result. Report the actual result, including rejection if it fails. |
| 1:45-2:10 | Show Repair a broken update with good HEAD~2 and bad HEAD. Explain bounded iterative repairs and unchanged tests; download the accepted patch if available. |
| 2:10-2:30 | Download report, show tested commit statuses and pause/resume/stop. Explain original source is untouched and public upstream commits retain authentic dates. |
| 2:30-2:40 | Public repository/setup link. State that test coverage limits conclusions and the app never guarantees a bug-free production system. |

Prepare and rehearse both runs before recording. If using saved evidence, label it
as a prior real run; do not describe mocked provider responses as live inference.
