import streamlit as st
import pandas as pd
import numpy as np
from bcb import sgs
from fredapi import Fred

st.set_page_config(
    page_title="Dashboard Portfel: Carry Trade & Fator de Hedge", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 Monitor Institucional: Diferencial de Juros (Carry Trade)")
st.markdown("""
Esta ferramenta compara as taxas de juros do Brasil e dos EUA para calcular o "prêmio" de investir no Brasil com proteção cambial.
Os cálculos utilizam o CDI diário e o Fed Funds, convertidos de forma padronizada para mostrar o ganho real do spread.
""")

@st.cache_data(show_spinner=False)
def extrair_cdi_fatiado(data_inicio, data_fim):
    data_atual = pd.to_datetime(data_inicio)
    data_final = pd.to_datetime(data_fim)
    pedacos = []
    
    while data_atual <= data_final:
        proxima_data = min(data_atual + pd.DateOffset(years=5), data_final)
        # Série 12: Taxa de juros - CDI (% ao dia)
        df_pedaco = sgs.get({'CDI_Diario_Pct': 12}, start=data_atual, end=proxima_data)
        pedacos.append(df_pedaco)
        data_atual = proxima_data + pd.Timedelta(days=1)
        
    return pd.concat(pedacos)

st.sidebar.header("Parâmetros de Extração")
api_key = st.sidebar.text_input("Chave API do FRED", type="password")
data_inicio = st.sidebar.date_input("Data de Início", pd.to_datetime("2000-01-01"))
data_fim = st.sidebar.date_input("Data Final", pd.to_datetime("today"))

if st.sidebar.button("Rodar Simulação"):
    if not api_key:
        st.sidebar.error("A chave da API do FRED é obrigatória.")
    else:
        with st.spinner("Processando e alinhando dados (isso pode levar alguns segundos)..."):
            try:
                fred = Fred(api_key=api_key)
                
                cdi = extrair_cdi_fatiado(data_inicio, data_fim)
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                fed_funds = fed_funds.to_frame(name='Fed_Funds_Anual_Pct')

                df = pd.merge(cdi, fed_funds, left_index=True, right_index=True, how='outer')
                df = df.ffill().dropna() 

                # 1. VITRINE PEDAGÓGICA (Taxas Anualizadas para leitura humana)
                # Transforma o CDI diário em Anual (Base 252)
                df['CDI_Anualizado_Pct'] = ((1 + (df['CDI_Diario_Pct'] / 100)) ** 252 - 1) * 100
                
                # O Spread Nominal Anualizado (Apenas para visualização rápida da diferença)
                df['Spread_Anual_Pct'] = df['CDI_Anualizado_Pct'] - df['Fed_Funds_Anual_Pct']

                # 2. MOTOR MATEMÁTICO (Fatores diários para capitalização exata)
                # Brasil: A taxa já é diária, basta transformar em fator
                df['Fator_BR'] = 1 + (df['CDI_Diario_Pct'] / 100)
                
                # EUA: A taxa é anual, precisamos dividir por 360 para achar o fator diário
                df['Fator_US'] = 1 + (df['Fed_Funds_Anual_Pct'] / 100 / 360)
                
                # O Fator final de Carry (Vento a favor BR / Vento contra US)
                df['Carry_Diario_Fator'] = df['Fator_BR'] / df['Fator_US']
                
                # Acúmulo do capital começando em Base 100
                df['Capital_Acumulado (Base 100)'] = 100 * df['Carry_Diario_Fator'].cumprod()

                # --- DASHBOARD VISUAL ---
                st.markdown("---")
                st.subheader("O Poder do Carry Trade Acumulado")
                st.line_chart(df['Capital_Acumulado (Base 100)'])

                st.markdown("### Resumo do Período (Médias Anualizadas)")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("CDI (Média Anual)", f"{df['CDI_Anualizado_Pct'].mean():.2f}% a.a.")
                col2.metric("Fed Funds (Média Anual)", f"{df['Fed_Funds_Anual_Pct'].mean():.2f}% a.a.")
                
                retorno_total_pct = df['Capital_Acumulado (Base 100)'].iloc[-1] - 100
                col3.metric("Ganho Total do Hedge", f"{retorno_total_pct:.2f}%")
                
                anos_passados = len(df) / 252
                cagr = ((df['Capital_Acumulado (Base 100)'].iloc[-1] / 100) ** (1 / anos_passados) - 1) * 100
                col4.metric("Ganho Médio Anualizado", f"{cagr:.2f}% a.a.")

                # --- TABELA DE DADOS ---
                st.markdown("---")
                st.subheader("Base de Dados (Visão Simplificada)")
                st.markdown("A tabela exibe as taxas anualizadas para facilitar a leitura. Os cálculos usaram as frações diárias corretas.")
                
                colunas_display = [
                    'CDI_Anualizado_Pct', 
                    'Fed_Funds_Anual_Pct', 
                    'Spread_Anual_Pct', 
                    'Carry_Diario_Fator', 
                    'Capital_Acumulado (Base 100)'
                ]
                
                st.dataframe(df[colunas_display].style.format({
                    'CDI_Anualizado_Pct': '{:.2f}%',
                    'Fed_Funds_Anual_Pct': '{:.2f}%',
                    'Spread_Anual_Pct': '{:.2f} p.p.',
                    'Carry_Diario_Fator': '{:.6f}',
                    'Capital_Acumulado (Base 100)': '{:.2f}'
                }))

                csv = df.to_csv(index=True, sep=';', decimal=',')
                st.download_button(
                    label="📥 Download Planilha (CSV)",
                    data=csv,
                    file_name='portfel_carry_trade_ajustado.csv',
                    mime='text/csv',
                )

            except Exception as e:
                st.error(f"Erro durante a execução: {e}")
