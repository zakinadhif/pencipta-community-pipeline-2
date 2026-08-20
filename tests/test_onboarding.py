from types import SimpleNamespace

from src.agents.onboarding import OnboardingInterviewer, OnboardingSession


class FakeResponses:
    def __init__(self, responses):
        self._responses = iter(responses)
        self.requests = []

    def create(self, **request):
        self.requests.append(request)
        return next(self._responses)


def response(*output, text=""):
    return SimpleNamespace(
        output=list(output),
        output_text=text,
        model_dump=lambda: {"output_text": text},
    )


def function_call(name, call_id):
    return SimpleNamespace(
        type="function_call",
        name=name,
        arguments="{}",
        call_id=call_id,
    )


def test_interviewer_executes_state_tool_before_replying():
    responses = FakeResponses(
        [
            response(function_call("getOnboardingState", "state-1")),
            response(text="What are you currently working on?"),
        ]
    )
    interviewer = OnboardingInterviewer(client=SimpleNamespace(responses=responses))
    session = OnboardingSession()
    session.add_user_answer("Hello")

    result = interviewer.next_turn(session)

    assert result["message"] == "What are you currently working on?"
    assert result["tool_events"][0]["name"] == "getOnboardingState"
    assert result["tool_events"][0]["result"]["meaningfulUserAnswers"] == 0
    assert responses.requests[0]["tool_choice"]["name"] == "getOnboardingState"
    assert responses.requests[1]["input"][-1]["type"] == "function_call_output"


def test_finish_tool_marks_session_complete():
    responses = FakeResponses(
        [
            response(function_call("getOnboardingState", "state-1")),
            response(function_call("finishOnboarding", "finish-1")),
            response(text="Thanks — your onboarding is complete."),
        ]
    )
    interviewer = OnboardingInterviewer(client=SimpleNamespace(responses=responses))
    session = OnboardingSession()
    session.add_user_answer("I build data systems and want help finding collaborators.")

    result = interviewer.next_turn(session)

    assert result["finished"] is True
    assert session.finished is True
    assert [event["name"] for event in result["tool_events"]] == [
        "getOnboardingState",
        "finishOnboarding",
    ]
