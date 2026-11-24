from app.main import update_player_condition


class RecordingConnection:
    def __init__(self):
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params


def test_player_condition_changes_sharpness_and_morale_by_result():
    for result, expected_delta in (("win", 4), ("draw", 1), ("loss", -4)):
        conn = RecordingConnection()
        update_player_condition(conn, "game-state", "club", result)

        assert "sharpness=GREATEST(20,LEAST(100,sharpness-5))" in conn.query
        assert "fatigue=LEAST(100,fatigue+12)" in conn.query
        assert conn.params == (expected_delta, expected_delta, "game-state", "club")
