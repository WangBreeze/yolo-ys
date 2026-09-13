"""Synchronous reference runtime with bounded steps and observed verification."""

from contextlib import ExitStack
from dataclasses import asdict
from time import monotonic_ns, sleep

from .contracts import fingerprint, matches
from .registry import registry_for


def validate_observation(context, state):
    settings = context.config["runtime"]
    if context.output_path(settings["stop_file"]).exists():
        raise ValueError("stop file present")
    age_ms = (monotonic_ns() - state.captured_ns) / 1e6
    if age_ms < 0 or age_ms > settings["max_frame_age_ms"]:
        raise ValueError("stale or invalid observation timestamp")
    if context.mode == "live" and (not state.focused or not state.window_id):
        raise ValueError("target window is not focused")


def validate_action(context, action):
    settings = context.config["runtime"]
    if action.duration_ms > settings["max_action_ms"]:
        raise ValueError("action duration exceeds profile limit")
    if action.kind == "key" and action.key not in settings["allowed_keys"]:
        raise ValueError(f"key {action.key} not in this game's allowed_keys")


class Application:
    def __init__(self, context, registry=None):
        self.context = context
        self.registry = registry or registry_for(context)
        self.stack = ExitStack()
        self.instances = {}

    def plugin(self, role):
        if role not in self.instances:
            plugin = self.registry.create(role, self.context)
            self.stack.callback(plugin.close)
            self.instances[role] = plugin
        return self.instances[role]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return self.stack.__exit__(*exc)

    def ingest(self, source):
        plan = self.plugin("tutorial").analyze(source)
        if plan.game != self.context.game:
            raise ValueError("tutorial game/version/profile differs from configuration")
        return self.plugin("memory").remember(plan)

    def run(self, plan, live=False):
        context = self.context
        if getattr(self, "ran", False):
            raise ValueError("create a new Application for each run to reset plugin state")
        self.ran = True
        if plan.game != context.game:
            raise ValueError("plan game/version/profile differs from configuration")
        if context.mode == "live" and not live:
            raise ValueError("live mode needs --live and an explicit target window profile")
        context.services["live_enabled"] = live
        capture = self.plugin("capture")
        perception = self.plugin("perception")
        planner = self.plugin("planner")
        policy = self.plugin("policy")
        controller = self.plugin("controller")
        if capture.mode != context.mode:
            raise ValueError("capture mode does not match runtime mode")
        if controller.mode not in (context.mode, "dry-run"):
            raise ValueError("controller mode does not match runtime mode")
        if context.mode == "replay" and controller.mode != "dry-run":
            raise ValueError("recorded video cannot drive live input")
        memory = self.plugin("memory")
        evidence_mode = "dry-run" if controller.mode == "dry-run" else context.mode
        provenance = {"plugins": self.registry.provenance(context),
                      "configuration_sha256": fingerprint(context.config)}
        run_id = memory.begin(plan, evidence_mode, provenance)
        status, reason, ticks, pending = "timeout", "tick budget exhausted", 0, None
        samples = []
        previous_sequence = -1
        try:
            for ticks in range(1, context.config["runtime"]["max_ticks"] + 1):
                started = monotonic_ns()
                frame = capture.capture()
                if frame is None:
                    status, reason = "blocked", "capture ended before completion"
                    break
                state = perception.perceive(frame)
                validate_observation(context, state)
                if state.sequence != frame.sequence or state.captured_ns != frame.captured_ns:
                    raise ValueError("perception changed frame identity or timestamp")
                if state.sequence <= previous_sequence:
                    raise ValueError("capture did not provide a new frame")
                previous_sequence = state.sequence
                decision = planner.decide(plan, state, monotonic_ns())
                memory.append(run_id, "observation", {"state": asdict(state), "decision": decision.status,
                                                       "step": decision.step.id if decision.step else None})
                if decision.status == "advance":
                    if pending is not None and pending["step_id"] == decision.step.id:
                        memory.append(run_id, "step_verified", dict(pending, after=asdict(state)))
                    pending = None
                elif decision.status == "complete":
                    if not matches(state.facts, plan.success):
                        raise ValueError("planner completion was not confirmed by observation")
                    status = "dry-run" if evidence_mode == "dry-run" else "success"
                    reason = "observed final conditions"
                    break
                elif decision.status == "blocked":
                    status, reason = "blocked", decision.reason
                    break
                elif decision.status == "act":
                    action = policy.choose(decision.step, state)
                    validate_action(context, action)
                    # Recheck freshness after a potentially slow policy inference.
                    validate_observation(context, state)
                    applied = controller.execute(action, state)
                    pending = {"step_id": decision.step.id, "goal": decision.step.goal,
                               "template": action.template(), "before": asdict(state),
                               "action": asdict(action), "applied": applied}
                    memory.append(run_id, "action", pending)
                elif decision.status != "wait":
                    raise ValueError(f"unknown planner status {decision.status}")
                elapsed_ms = (monotonic_ns() - started) / 1e6
                samples.append(elapsed_ms)
                sleep(max(0, 1 / context.config["runtime"]["tick_hz"] - elapsed_ms / 1000))
        except KeyboardInterrupt:
            status, reason = "stopped", "interrupted"
        except Exception as exc:
            status, reason = "error", f"{type(exc).__name__}: {exc}"
        finally:
            try:
                controller.release_all()
            except Exception as exc:
                status, reason = "error", f"input release failed: {exc}"
            memory.finish(run_id, status, reason)
        samples.sort()
        result = {"run_id": run_id, "plan_id": plan.id, "mode": evidence_mode,
                  "status": status, "reason": reason, "ticks": ticks,
                  "tick_p95_ms": round(samples[min(len(samples)-1, int(len(samples)*0.95))], 3) if samples else None}
        return result
