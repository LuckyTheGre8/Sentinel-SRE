from sentinel_ops.demo import smoke


async def test_full_judge_path_twice(tmp_path):
    results = await smoke(2, root=tmp_path)
    assert len(results) == 2
    assert results[0]["investigation_id"] != results[1]["investigation_id"]
    for result in results:
        assert result["initial_http"] == result["after_pr_http"] == 503
        assert result["final_http"] == 200 and result["result"] == "resolved"
        assert result["confirmation_required"] and result["restart_replay_identical"]
        assert result["pr_count"] == 1 and result["ranked_first"] == "b" * 40
