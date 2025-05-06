import streamlit as st
from google import genai
from google.genai.types import Tool, GenerateContentConfig, GoogleSearch, Content, Part
import pandas as pd
import json
import glob
import pdfkit
import markdown

# to update
after = '2025-04-01'
price = {
    'gemini-2.5-flash-preview-04-17': {'input': 0.15, 'output': 0.6, 'thinking': 3.5},
}

prompt_token_count = 0
candidates_token_count = 0
cached_content_token_count = 0
thoughts_token_count = 0
tool_use_prompt_token_count = 0
total_token_count = 0
def accumulate_token_count(usage_metadata):
    global prompt_token_count, candidates_token_count, cached_content_token_count, thoughts_token_count, tool_use_prompt_token_count, total_token_count
    prompt_token_count += usage_metadata.prompt_token_count
    candidates_token_count += usage_metadata.candidates_token_count
    cached_content_token_count += usage_metadata.cached_content_token_count if usage_metadata.cached_content_token_count else 0
    thoughts_token_count += usage_metadata.thoughts_token_count if usage_metadata.thoughts_token_count else 0
    tool_use_prompt_token_count += usage_metadata.tool_use_prompt_token_count if usage_metadata.tool_use_prompt_token_count else 0
    total_token_count += usage_metadata.total_token_count
def cost():
    return round((prompt_token_count * price[model]['input'] + thoughts_token_count * price[model]['thinking'] + candidates_token_count * price[model]['output'])/1e6, 2)

user_prompt_type = '1'

def get_relevant_ids(csv_df_json) -> str:
    system_prompt = 'Given a user prompt, identify the most relevant ids in the JSON below, output only the ids and no other text.\n'
    system_prompt += st.session_state.knowledge[csv_df_json]
    try:
        response = client.models.generate_content(
            model=model,
            contents=user_prompt,
            config=GenerateContentConfig(
                system_instruction=system_prompt,
                response_mime_type="application/json",
            )
        )
        result = response.text
        assert type(json.loads(result)) is list
        accumulate_token_count(response.usage_metadata)
    except Exception as e:
        st.code(f"Errrr: {e}")
        result = '[]'
    finally:
        st.code(csv_df_json.replace('df.iloc[:,:2].to_json', result))
        return result

def get_retrieval(csv_file) -> str:
    try:
        ids = json.loads(get_relevant_ids(csv_file + ' => df.iloc[:,:2].to_json'))
    except json.JSONDecodeError as e:
        st.code(f"JSONDecodeError: {e}")
        ids = None
    if ids:
        if type(ids[0]) is dict:
            ids = [int(_id['id']) for _id in ids]
        else:
            ids = [int(_id) for _id in ids]

        if user_prompt_type == '1':
            df = st.session_state.knowledge[csv_file]
            df = df[df['id'].isin(ids)]
        if user_prompt_type == '2':
            df = pd.DataFrame(columns=['id', 'html'])
            df['id'] = ids
            htmls = []
            for _id in ids:
                with open(csv_file.replace('_log', str(_id)).replace('csv', 'html')) as f:
                    htmls.append(''.join(f.readlines()))
            df['html'] = htmls
        return df.to_json(orient='records', force_ascii=False)
    else:
        return ''

client = genai.Client(api_key=st.secrets['GEMINI_API_KEY'])

if 'knowledge' not in st.session_state:
    st.session_state.knowledge = {}
    for csv_file in glob.glob('knowledge/*.csv') + glob.glob('knowledge/*/*/*.csv'):
        df = pd.read_csv(csv_file)
        # quickie, blog, edm
        if 'date' in df.columns:
            df = df[df['date'] > after]
        st.session_state.knowledge[csv_file] = df
        st.session_state.knowledge[csv_file + ' => df.iloc[:,:2].to_json'] = df.iloc[:,:2].to_json(orient='records', force_ascii=False)

with st.sidebar:
    st.title("📝 MM Business Report")
    system_prompt = st.text_area("Our System Prompt", value='''
- 你是財經M平方（MacroMicro，簡稱MM）總經數據平台的AI系統
- 你會根據用戶的需求，生成商業報告
- 報告內容整合MM提供的及網路搜尋的資料及數據
- 使用 Markdown 語法編排內容，善用格式文字、對照表、超連結（Hyperlink），不要直接使用網址（URL）
- 當用戶以英文提問，你務必以英文生成報告內容
''', height=400)
    model = st.selectbox('Model', price.keys())

with st.container():
    # subheader_text = dict(zip(site_languages, subheader_texts))[site_language]
    # st.subheader(subheader_text)
    user_prompt = st.text_area("Business User Prompt", value='''
You are a financial news analyst. Generate a weekly macroeconomic and capital market briefing similar in structure and tone to an institutional "Macro Weekly" newsletter.
Structure the content into bullet points, grouped by sections such as:
- Capital Market Highlights
- Macroeconomic Data
- Industry & Trade (including Retail, Amazon, Tariffs)
- China-related Developments
- Consumer Life (Food, Housing, Transport, Entertainment)
- Big Tech (Google, Meta, Microsoft)
- AI & Devices
- Healthcare

Each section should be concise, information-dense, and updated to reflect the latest weekly developments. Use neutral tone, and occasionally include quotes, percentages, and comparisons if relevant.
Include US policy, global market reaction, company earnings, tech developments, and any geopolitical tensions.
Target audience: investment professionals and macroeconomic analysts.
''', height=500)
    submit_button = st.button("Generating report, just a few minutes...")
    if submit_button and user_prompt:
        # if retrieval := get_retrieval('knowledge/chart.csv'):
        #     system_prompt += f'\n- MM圖表的資料\n```{retrieval}```'
        #     system_prompt += f'\n網址規則 https://www.macromicro.me/charts/{{id}}/{{slug}}'
        if retrieval := get_retrieval('knowledge/quickie.csv'):
            system_prompt += f'\n- MM短評的資料\n```{retrieval}```'
            system_prompt += f'\n網址規則 https://www.macromicro.me/quickie?id={{id}}'
        if retrieval := get_retrieval('knowledge/blog.csv'):
            system_prompt += f'\n- MM部落格的資料\n```{retrieval}```'
            system_prompt += f'\n網址規則 https://www.macromicro.me/blog/{{slug}}'
        if retrieval := get_retrieval('knowledge/edm.csv'):
            system_prompt += f'\n- MM獨家報告的資料\n```{retrieval}```'
            system_prompt += f'\n網址規則 https://www.macromicro.me/mails/edm/tc/display/{{id}}'
        st.code(system_prompt)
        try:
            response = client.models.generate_content(
                model=model,
                contents=user_prompt,
                config=GenerateContentConfig(
                    tools=[Tool(google_search=GoogleSearch())],
                    system_instruction=system_prompt,
                    response_mime_type="text/plain",
                ),
            )
            result = response.text
            accumulate_token_count(response.usage_metadata)
        except Exception as e:
            st.code(f"Errrr: {e}")
            result = '抱歉，請稍後再試。。。'
        finally:
            st.badge(f'{prompt_token_count} input tokens + {thoughts_token_count} thinking tokens + {candidates_token_count} output tokens ≒ {cost()} USD ( when Google Search < 500 Requests/Day )', icon="💰", color="green")
            report_text = st.text_area("Generated report (editable)", value=result, height=1000)
            
            if st.download_button(
                label="Download as PDF",
                data=pdfkit.from_string(markdown.markdown(report_text), False),
                file_name="business_report.pdf",
                mime="application/pdf",
            ):
                st.success("PDF downloaded successfully!")