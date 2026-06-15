import unittest
from types import SimpleNamespace
from unittest.mock import patch

from langchain_core.messages import HumanMessage

import agent_graph


def _state(text: str) -> dict:
    return {"messages": [HumanMessage(content=text)]}


class FakeSupervisorModel:
    def __init__(self, next_value: str, response: str = ""):
        self.next_value = next_value
        self.response = response
        self.calls = []

    def invoke(self, *args, **kwargs):
        self.calls.append((args, kwargs))
        return SimpleNamespace(next=self.next_value, response=self.response)


class SupervisorRoutingTests(unittest.TestCase):
    def test_weather_query_uses_rule_based_researcher_route(self):
        state = _state("今天上海天气怎么样？")
        fake_model = FakeSupervisorModel("chat_agent")
        with patch("agent_graph.supervisor_model", fake_model):
            update = agent_graph.supervisor_node(state)

        self.assertEqual(fake_model.calls, [])
        self.assertEqual(update["next"], "researcher")
        self.assertEqual(agent_graph.route_after_supervisor(update), "researcher")

    def test_scope_context_is_removed_before_rule_routing(self):
        state = _state(
            "当前公司ID：starlinke\n"
            "当前公司名称：starlinke\n"
            "当前用户ID：user-a\n"
            "当前品牌ID：default-brand\n"
            "当前项目ID：project-a\n\n"
            "今天上海天气怎么样？"
        )

        self.assertEqual(agent_graph._rule_based_supervisor_route(state), "researcher")

    def test_plain_chat_routes_to_chat_agent(self):
        fake_model = FakeSupervisorModel("chat_agent")
        with patch("agent_graph.supervisor_model", fake_model):
            update = agent_graph.supervisor_node(_state("你好"))

        self.assertEqual(update["next"], "chat_agent")
        self.assertEqual(agent_graph.route_after_supervisor(update), "chat_agent")
        self.assertEqual(fake_model.calls[0][1]["config"]["tags"], [agent_graph.TAG_NOSTREAM])

    def test_memory_manager_requires_human_review(self):
        fake_model = FakeSupervisorModel("memory_manager")
        with patch("agent_graph.supervisor_model", fake_model):
            update = agent_graph.supervisor_node(_state("帮我记住我喜欢黑咖啡"))

        self.assertEqual(update["next"], "memory_manager")
        self.assertEqual(agent_graph.route_after_supervisor(update), "human_review")

    def test_knowledge_manager_requires_human_review(self):
        fake_model = FakeSupervisorModel("knowledge_manager")
        with patch("agent_graph.supervisor_model", fake_model):
            update = agent_graph.supervisor_node(_state("保存这段笔记：SSE 是服务器推送事件"))

        self.assertEqual(update["next"], "knowledge_manager")
        self.assertEqual(agent_graph.route_after_supervisor(update), "human_review")

    def test_code_generator_requires_human_review(self):
        fake_model = FakeSupervisorModel("code_generator")
        with patch("agent_graph.supervisor_model", fake_model):
            update = agent_graph.supervisor_node(_state("帮我生成一个活动落地页"))

        self.assertEqual(update["next"], "code_generator")
        self.assertEqual(agent_graph.route_after_supervisor(update), "human_review")


if __name__ == "__main__":
    unittest.main()
