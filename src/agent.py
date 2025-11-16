import ast
import inspect
import os
import platform
import re
from string import Template
from typing import Any, Callable, Dict, List, Tuple

from openai import OpenAI

from .prompts import react_system_prompt_template
from .settings import BASE_URL, DEFAULT_MODEL_NAME, OPENROUTER_API_KEY

class ReActAgent:
    def __init__(
        self,
        tools: List[Callable],
        model: str = DEFAULT_MODEL_NAME,
        project_directory: str = ".",
    ) -> None:
        # 工具：函数名 -> 函数本体
        self.tools: Dict[str, Callable[..., Any]] = {
            func.__name__: func for func in tools
        }
        self.model_name = model
        self.project_directory = project_directory

        # OpenRouter Client
        self.client = OpenAI(
            base_url=BASE_URL,
            api_key=OPENROUTER_API_KEY,
        )

    # ========= 对话主循环 =========
    def run(self, user_input: str, max_steps: int = 16) -> str:
        messages = [
            {
                "role": "system",
                "content": self.render_system_prompt(react_system_prompt_template),
            },
            {
                "role": "user",
                "content": f"<question>{user_input}</question>",
            },
        ]

        last_content = ""

        for step in range(max_steps):
            print(f"\n===== ReAct step {step + 1} / {max_steps} =====")
            content = self.call_model(messages)
            last_content = content

            if (
                "<action>" not in content
                and "<final_answer>" not in content
                and "<thought>" not in content
            ):
                print(
                    "\n[INFO] 本轮模型没有使用 XML 标签，自动将整段内容视作最终答案。"
                )
                return content.strip()

            # Thought
            thought_match = re.search(
                r"<thought>(.*?)</thought>", content, re.DOTALL
            )
            if thought_match:
                thought = thought_match.group(1).strip()
                print(f"\n💭 Thought: {thought}")

            # final_answer
            final_match = re.search(
                r"<final_answer>(.*?)</final_answer>", content, re.DOTALL
            )
            if final_match:
                return final_match.group(1).strip()

            # action
            action_match = re.search(
                r"<action>(.*?)</action>", content, re.DOTALL
            )
            if not action_match:
                print(
                    "\n[INFO] 本轮没有 <action>，但已经有内容，作为最终答案返回。"
                )
                return content.strip()

            action_str = action_match.group(1).strip()
            tool_name, args = self.parse_action(action_str)
            print(f"\n🔧 Action: {tool_name}({', '.join(map(str, args))})")

            if tool_name == "run_terminal_command":
                cont = input("\n是否继续执行终端命令？(Y/N)：")
                if cont.lower() != "y":
                    print("操作已取消。")
                    return "操作被用户取消"

            try:
                observation = self.tools[tool_name](*args)
            except KeyError:
                observation = f"工具 {tool_name} 未定义，请只使用提供的工具列表。"
            except Exception as e:  # noqa: BLE001
                observation = f"工具 {tool_name} 执行错误：{e}"

            print(f"\n🔍 Observation：{observation}")
            messages.append(
                {
                    "role": "user",
                    "content": f"<observation>{observation}</observation>",
                }
            )

        print(
            "\n[WARN] 已达到最大 ReAct 步数，仍未获得 <final_answer>，返回最后一轮模型输出。"
        )
        return last_content.strip()

    # ========= 工具 & 环境描述 =========
    def get_tool_list(self) -> str:
        """生成工具列表字符串，包含函数签名和简要说明"""
        descs = []
        for func in self.tools.values():
            name = func.__name__
            signature = str(inspect.signature(func))
            doc = inspect.getdoc(func) or ""
            descs.append(f"- {name}{signature}: {doc}")
        return "\n".join(descs)

    def render_system_prompt(self, system_prompt_template: str) -> str:
        """用工具列表 & 文件列表渲染 system prompt 模板"""
        tool_list = self.get_tool_list()
        file_list = ", ".join(
            os.path.abspath(os.path.join(self.project_directory, f))
            for f in os.listdir(self.project_directory)
        )
        return Template(system_prompt_template).substitute(
            operating_system=self.get_operating_system_name(),
            tool_list=tool_list,
            file_list=file_list,
        )

    # ========= 调用 OpenRouter 模型 =========
    def call_model(self, messages: List[Dict[str, str]]) -> str:
        """调用 OpenRouter 上的聊天模型"""
        print("\n\n正在请求 OpenRouter 模型……")

        response = self.client.chat.completions.create(
            model=self.model_name,
            messages=messages,
            max_tokens=2048,
            temperature=0.2,
        )

        content = response.choices[0].message.content
        messages.append({"role": "assistant", "content": content})
        return content

    # ========= 解析 <action> 里的函数调用 =========
    def parse_action(self, code_str: str) -> Tuple[str, List[Any]]:
        """
        把形如 'read_file("xxx")' 的字符串解析成 (函数名, [参数列表])
        支持字符串里有括号、逗号、换行等情况。
        """
        match = re.match(r"(\w+)\((.*)\)", code_str, re.DOTALL)
        if not match:
            raise ValueError(f"Invalid function call syntax: {code_str}")

        func_name = match.group(1)
        args_str = match.group(2).strip()

        args: List[Any] = []
        current_arg = ""
        in_string = False
        string_char = None
        paren_depth = 0
        i = 0

        while i < len(args_str):
            char = args_str[i]

            if not in_string:
                if char in ['"', "'"]:
                    in_string = True
                    string_char = char
                    current_arg += char
                elif char == "(":
                    paren_depth += 1
                    current_arg += char
                elif char == ")":
                    paren_depth -= 1
                    current_arg += char
                elif char == "," and paren_depth == 0:
                    args.append(self._parse_single_arg(current_arg.strip()))
                    current_arg = ""
                else:
                    current_arg += char
            else:
                current_arg += char
                if char == string_char and (i == 0 or args_str[i - 1] != "\\"):
                    in_string = False
                    string_char = None
            i += 1

        if current_arg.strip():
            args.append(self._parse_single_arg(current_arg.strip()))

        return func_name, args

    def _parse_single_arg(self, arg_str: str) -> Any:
        """解析单个参数成 Python 对象（字符串 / 数字 / 列表 等）"""
        arg_str = arg_str.strip()

        if (arg_str.startswith('"') and arg_str.endswith('"')) or (
            arg_str.startswith("'") and arg_str.endswith("'")
        ):
            inner = arg_str[1:-1]
            inner = inner.replace('\\"', '"').replace("\\'", "'")
            inner = inner.replace("\\n", "\n").replace("\\t", "\t")
            inner = inner.replace("\\r", "\r").replace("\\\\", "\\")
            return inner

        try:
            return ast.literal_eval(arg_str)
        except (SyntaxError, ValueError):
            return arg_str

    @staticmethod
    def get_operating_system_name() -> str:
        os_map = {"Darwin": "macOS", "Windows": "Windows", "Linux": "Linux"}
        return os_map.get(platform.system(), "Unknown")
