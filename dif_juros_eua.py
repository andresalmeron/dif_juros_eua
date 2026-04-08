import streamlit as st
import pandas as pd
import numpy as np
from bcb import sgs
from fredapi import Fred

st.set_page_config(
    page_title="Portfel: Carry vs. Câmbio", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚖️ Carry Trade vs. Variação Cambial (USDBRL)")
st.markdown("""
Analise o custo de oportunidade do hedge. Esta ferramenta compara o retorno acumulado do 
**Diferencial de Juros (Carry)** contra a **Valorização do Dólar (Câmbio)**.
""")

@st.cache_data(show_spinner=False)
def extrair_dados_bcb(data_inicio, data_fim):
    data_atual = pd.to_datetime(data_inicio)
    data_final = pd.to_datetime(data_fim)
    pedacos = []
    
    while data_atual <= data_final:
        proxima_data = min(data_atual + pd.DateOffset(years=5), data_final)
        # Série 12: CDI Diário | Série 1: USDBRL (Venda)
        df_lote = sgs.get({'CDI_Diario': 12, 'USDBRL': 1}, start=data_atual, end=proxima_data)
        pedacos.append(df_lote)
        data_atual = proxima_data + pd.Timedelta(days=1)
        
    return pd.concat(pedacos)

st.sidebar.header("Parâmetros")
api_key = st.sidebar.text_input("Chave API do FRED", type="password")
data_inicio = st.sidebar.date_input("Início", pd.to_datetime("2010-01-01"))
data_fim = st.sidebar.date_input("Fim", pd.to_datetime("today"))

if st.sidebar.button("Simular Comparativo"):
    if not api_key:
        st.sidebar.error("Insira a chave do FRED.")
    else:
        with st.spinner("Cruzando dados de Juros e Câmbio..."):
            try:
                # 1. Extração
                fred = Fred(api_key=api_key)
                bcb_data = extrair_dados_bcb(data_inicio, data_fim)
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                
                # 2. Alinhamento
                df = pd.merge(bcb_data, fed_funds.to_frame('Fed_Funds'), left_index=True, right_index=True, how='outer')
                df = df.ffill().dropna()

                # 3. Cálculos de Carry (Juros)
                df['Fator_BR'] = 1 + (df['CDI_Diario'] / 100)
                df['Fator_US'] = 1 + (df['Fed_Funds'] / 100 / 360)
                df['Carry_Diario'] = df['Fator_BR'] / df['Fator_US']
                df['Carry_Acumulado'] = 100 * df['Carry_Diario'].cumprod()

                # 4. Cálculos de Câmbio (Moeda)
                # Retorno acumulado do dólar partindo da base 100
                df['Cambio_Acumulado'] = 100 * (df['USDBRL'] / df['USDBRL'].iloc[0])

                # 5. Visualização
                st.subheader("Quem rendeu mais: O Diferencial de Juros ou o Dólar?")
                st.line_chart(df[['Carry_Acumulado', 'Cambio_Acumulado']])

                st.markdown("### Comparativo de Retornos Totais")
                c1, c2, c3 = st.columns(3)
                
                ret_carry = df['Carry_Acumulado'].iloc[-1] - 100
                ret_cambio = df['Cambio_Acumulado'].iloc[-1] - 100
                
                c1.metric("Retorno Total do Carry", f"{ret_carry:.2f}%")
                c2.metric("Valorização do Dólar (FX)", f"{ret_cambio:.2f}%")
                
                vencedor = "Carry Trade" if ret_carry > ret_cambio else "Dólar (FX)"
                diff = abs(ret_carry - ret_cambio)
                c3.subheader(f"Vencedor: {vencedor}")
                st.info(f"A diferença entre as duas estratégias no período foi de **{diff:.2f} pontos percentuais**.")

                # Tabela detalhada
                st.markdown("---")
                st.subheader("Dados Brutos para Auditoria")
                df_view = df[['USDBRL', 'CDI_Diario', 'Fed_Funds', 'Carry_Acumulado', 'Cambio_Acumulado']]
                st.dataframe(df_view.style.format("{:.2f}"))

            except Exception as e:
                st.error(f"Erro: {e}")
