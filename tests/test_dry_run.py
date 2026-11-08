def test_dry_run_exercises_gate_without_a_transport(capsys):
    from examples.dry_run import main
    main()
    output = capsys.readouterr().out
    assert output.splitlines() == [
        "no consent: block (no_consent)",
        "approved routine: pass (routine)",
        "unanswered thread: approve (unanswered)",
        "after observed reply: pass (routine)",
        "changed wording: approve (unapproved_wording)",
        "after STOP: block (suppressed)",
        "decisions logged: 7; transports invoked: 0",
    ]
