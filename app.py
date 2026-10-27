import os
import re

import streamlit as st
from openai import APIConnectionError, APIStatusError, AuthenticationError, OpenAI, RateLimitError


def load_local_env() -> None:
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding="utf-8") as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            # Streamlit은 같은 프로세스에서 앱을 다시 실행하므로,
            # 사용자가 .env를 수정한 뒤에도 최신 값을 반영해야 합니다.
            os.environ[key.strip()] = value.strip().strip('"').strip("'")


load_local_env()

st.set_page_config(page_title="친절한 AI 챗봇", page_icon="💬", layout="centered")


def get_client() -> OpenAI | None:
    # 사용자가 .env에 직접 입력하는 키 이름을 그대로 사용합니다.
    api_key = os.getenv("openai_api_key", "").strip()
    if not api_key:
        return None
    return OpenAI(api_key=api_key)


def load_page_index() -> list[dict[str, str]]:
    """목차 파일에서 페이지 번호, 제목, 요약만 읽어 검색용 색인을 만듭니다."""
    index_path = os.path.join(os.path.dirname(__file__), "카본매트_KME_페이지별_검색목록.md")
    if not os.path.exists(index_path):
        return []
    text = open(index_path, encoding="utf-8").read()
    pattern = re.compile(r"##\s+(\d+)쪽\s*\|\s*(.+?)\n\n요약:\s*(.+)")
    return [
        {"page": page, "title": title.strip(), "summary": summary.strip()}
        for page, title, summary in pattern.findall(text)
    ]


def find_related_pages(question: str, limit: int = 5) -> list[dict[str, str]]:
    """질문과 목차의 제목·요약을 비교합니다. 결과는 챗봇 입력에 포함하지 않습니다."""
    query_terms = set(re.findall(r"[가-힣A-Za-z0-9]+", question.lower()))
    # 사용자가 자주 쓰는 표현을 설명서 목차의 표현으로 확장합니다.
    aliases = {
        "더블매트": {"더블", "좌우", "양쪽"},
        "양쪽": {"좌우", "더블"},
        "양쪽온도": {"좌우", "온도"},
        "똑같이": {"동기화", "동일", "같은"},
        "같게": {"동기화", "동일", "같은"},
        "맞추": {"설정", "조절"},
    }
    for term in list(query_terms):
        query_terms.update(aliases.get(term, set()))
    # '더블매트'처럼 붙여 쓴 표현도 핵심 단어를 찾을 수 있게 합니다.
    if "더블매트" in question.replace(" ", "").lower():
        query_terms.update({"더블", "좌우", "온도", "동기화"})
    scored = []
    normalized_question = question.replace(" ", "").lower()
    asks_about_both_sleep_modes = "취침기능" in normalized_question and "수면기능" in normalized_question
    for item in load_page_index():
        searchable = f"{item['title']} {item['summary']}".lower()
        score = sum(1 for term in query_terms if len(term) > 1 and term in searchable)
        if asks_about_both_sleep_modes and item["page"] in {"14", "15"}:
            score += 6
        # 더블/퀸/킹 매트의 좌우 온도 맞추기 질문은 실제 설치·사용 절차가
        # 설명된 20쪽을 가장 먼저 보여줍니다.
        if (
            item["page"] == "20"
            and any(word in normalized_question for word in ("더블매트", "퀸", "킹", "양쪽"))
            and any(word in normalized_question for word in ("온도", "똑같", "같게", "맞추"))
        ):
            score += 5
        if score:
            scored.append((score, item))
    scored.sort(key=lambda pair: (-pair[0], int(pair[1]["page"])))
    return [item for _, item in scored[:limit]]


st.title("💬 친절한 AI 챗봇")
st.caption("궁금한 점을 자유롭게 입력해 보세요.")

with st.sidebar:
    st.header("챗봇 설정")
    system_prompt = st.text_area(
        "시스템 프롬프트",
        value=st.session_state.get(
            "system_prompt",
            "카본매트 사용설명서에 근거가 있는 내용만 답변하세요. 설명서에 없는 내용이나 확인할 수 없는 내용은 추측하지 말고 '사용설명서에서 확인되지 않는 내용입니다'라고 안내하세요. 필요한 경우 고객상담실에 문의하도록 안내하세요. 답변은 친절하고 알기 쉽게 작성하세요.",
        ),
        height=180,
        help="챗봇의 말투와 답변 방식을 직접 지정할 수 있습니다.",
    )
    st.session_state.system_prompt = system_prompt
    st.divider()
    st.caption(f"모델: {os.getenv('model_name', 'gpt-5.6-luna')}")
    if st.button("대화 초기화", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

if "messages" not in st.session_state:
    st.session_state.messages = []

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

if prompt := st.chat_input("메시지를 입력하세요"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    related_pages = find_related_pages(prompt)
    with st.expander("근거 페이지", expanded=True):
        if related_pages:
            for item in related_pages:
                st.markdown(f"**근거 페이지: {item['page']}쪽 — {item['title']}**")
                st.caption(f"선택 근거: {item['summary']}")
            question_without_spaces = prompt.replace(" ", "")
            if any(word in question_without_spaces for word in ("취침", "수면")):
                st.markdown(
                    "**기능 구분 및 상세 근거**\n\n"
                    "- **14쪽 취침기능:** 33℃로 **9시간 동안 유지**한 뒤 자동으로 전원이 꺼집니다. "
                    "분리난방에서는 현재 작동 중인 좌측 또는 우측에만 취침기능을 적용할 수 있습니다.\n"
                    "- **15쪽 수면기능:** 사용자가 설정한 온도에서 시작해 **처음 3시간 동안 5℃ 낮아지도록** "
                    "천천히 조절하고, 설정 종료 **2시간 전부터 초기 설정온도로 복귀**합니다. 설정 시간은 "
                    "**5~10시간** 중 선택하며, 종료 후 자동으로 꺼집니다.\n\n"
                    "수면기능 시간별 구성: **5시간(3시간 감소·0시간 유지·2시간 복귀), "
                    "6시간(3·1·2), 7시간(3·2·2), 8시간(3·3·2), 9시간(3·4·2), "
                    "10시간(3·5·2)**"
                )
        else:
            st.caption("목차에서 직접 연결되는 관련 페이지를 찾지 못했습니다.")

    if not related_pages:
        unknown_answer = (
            "죄송하지만 해당 내용은 현재 사용설명서에서 확인되지 않습니다. "
            "정확한 안내가 필요하시면 귀뚜라미 고객상담실로 문의해 주세요."
        )
        with st.chat_message("assistant"):
            st.info(unknown_answer)
        st.session_state.messages.append({"role": "assistant", "content": unknown_answer})
        st.stop()

    client = get_client()
    if client is None:
        with st.chat_message("assistant"):
            st.error(".env 파일에 openai_api_key를 입력한 뒤 앱을 다시 실행해 주세요.")
    else:
        with st.chat_message("assistant"):
            try:
                response = client.chat.completions.create(
                    model=os.getenv("model_name", "gpt-5.6-luna"),
                    messages=[
                        {"role": "system", "content": system_prompt},
                        *st.session_state.messages,
                    ],
                )
                answer = response.choices[0].message.content or "답변을 생성하지 못했습니다."
                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except APIConnectionError:
                st.error(
                    "OpenAI 서버에 연결하지 못했습니다. 인터넷 연결, 방화벽 또는 프록시 설정을 확인한 뒤 다시 시도해 주세요."
                )
            except AuthenticationError:
                st.error("OpenAI API 키가 유효하지 않습니다. .env의 openai_api_key 값을 확인해 주세요.")
            except RateLimitError:
                st.error("OpenAI 사용 한도에 도달했습니다. 결제·사용량 한도를 확인해 주세요.")
            except APIStatusError as error:
                st.error(f"OpenAI 요청이 거부되었습니다 ({error.status_code}). 모델명과 API 사용 권한을 확인해 주세요.")
            except Exception as error:
                st.error(f"답변을 생성하는 중 오류가 발생했습니다: {error}")
