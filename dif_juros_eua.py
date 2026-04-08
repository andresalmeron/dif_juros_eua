import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from bcb import sgs
from fredapi import Fred
from datetime import date

# 1. Configurações da Página
st.set_page_config(
    page_title="Portfel: Carry vs. Câmbio", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("⚖️ Carry Trade vs. Variação Cambial (USDBRL)")
st.markdown("""
Analise o custo de oportunidade do hedge cambial com precisão institucional. 
Compare o retorno do **Diferencial de Juros (Carry)** contra a **Valorização do Dólar (FX)**.
A planilha de auditoria completa pode ser baixada ao final da página.
""")

# --- MOTOR DE EXTRAÇÃO COM CHUNKING ---
@st.cache_data(show_spinner=False)
def extrair_dados_completos(data_inicio, data_fim):
    data_atual = pd.to_datetime(data_inicio)
    data_final = pd.to_datetime(data_fim)
    pedacos = []
    
    while data_atual <= data_final:
        proxima_data = min(data_atual + pd.DateOffset(years=8), data_final)
        df_lote = sgs.get({'CDI_Diario': 12, 'USDBRL': 1}, start=data_atual, end=proxima_data)
        pedacos.append(df_lote)
        data_atual = proxima_data + pd.Timedelta(days=1)
        
    return pd.concat(pedacos)

# 2. Sidebar com Travas de Data
st.sidebar.header("Parâmetros de Análise")
api_key = st.sidebar.text_input("Chave API do FRED", type="password")

hoje = date.today()
data_min_possivel = date(1995, 1, 1) 

data_inicio = st.sidebar.date_input(
    "Data de Início", 
    value=date(2015, 1, 1), 
    min_value=data_min_possivel, 
    max_value=hoje
)

data_fim = st.sidebar.date_input(
    "Data Final", 
    value=hoje, 
    min_value=data_inicio, 
    max_value=hoje
)

# 3. Execução
if st.sidebar.button("Simular"):
    if not api_key:
        st.sidebar.error("Insira a chave do FRED.")
    else:
        with st.spinner("Calculando spreads e capitalização..."):
            try:
                # Extração
                fred = Fred(api_key=api_key)
                bcb_data = extrair_dados_completos(data_inicio, data_fim)
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                
                # Alinhamento
                df = pd.merge(bcb_data, fed_funds.to_frame('Fed_Funds'), left_index=True, right_index=True, how='outer')
                df = df.ffill().dropna()

                # Cálculos de Juros e Fatores
                df['CDI_Anualizado'] = ((1 + (df['CDI_Diario'] / 100)) ** 252 - 1) * 100
                df['Fator_BR'] = 1 + (df['CDI_Diario'] / 100)
                df['Fator_US'] = 1 + (df['Fed_Funds'] / 100 / 360)
                df['Carry_Diario'] = df['Fator_BR'] / df['Fator_US']
                df['Carry_Acumulado'] = 100 * df['Carry_Diario'].cumprod()

                # Cálculos de Câmbio
                df['Cambio_Acumulado'] = 100 * (df['USDBRL'] / df['USDBRL'].iloc[0])

                # 4. MÉTRICAS
                anos_totais = (pd.to_datetime(data_fim) - pd.to_datetime(data_inicio)).days / 365.25
                
                ret_carry_total = df['Carry_Acumulado'].iloc[-1] - 100
                ret_cambio_total = df['Cambio_Acumulado'].iloc[-1] - 100
                
                cagr_carry = ((df['Carry_Acumulado'].iloc[-1] / 100) ** (1 / anos_totais) - 1) * 100
                cagr_cambio = ((df['Cambio_Acumulado'].iloc[-1] / 100) ** (1 / anos_totais) - 1) * 100

                # --- VISUALIZAÇÃO COM PLOTLY ---
                fig = go.Figure()
                fig.add_trace(go.Scatter(x=df.index, y=df['Carry_Acumulado'], name='Carry Trade (Juros BR-US)', line=dict(color='#00CC96', width=2.5)))
                fig.add_trace(go.Scatter(x=df.index, y=df['Cambio_Acumulado'], name='Câmbio (USDBRL)', line=dict(color='#EF553B', width=2.5)))
                
                fig.update_layout(
                    title="Evolução Patrimonial: Carry vs. Câmbio (Base 100)",
                    xaxis_title="Data",
                    yaxis_title="Valor Acumulado",
                    hovermode="x unified",
                    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
                    margin=dict(l=0, r=0, t=50, b=0),
                    xaxis=dict(range=[df.index.min(), df.index.max()], autorange=False)
                )
                st.plotly_chart(fig, use_container_width=True)

                # Painel de Métricas
                st.markdown("### Comparativo de Performance")
                col1, col2 = st.columns(2)
                
                with col1:
                    st.write("**Estratégia: Carry Trade (Hedge)**")
                    st.metric("Retorno Acumulado", f"{ret_carry_total:.2f}%")
                    st.metric("Retorno Anualizado (CAGR)", f"{cagr_carry:.2f}% a.a.")
                
                with col2:
                    st.write("**Estratégia: Câmbio (Exposição em Dólar)**")
                    st.metric("Retorno Acumulado", f"{ret_cambio_total:.2f}%")
                    st.metric("Retorno Anualizado (CAGR)", f"{cagr_cambio:.2f}% a.a.")

                st.markdown("---")
                
                # --- PREPARAÇÃO DOS DADOS PARA AUDITORIA (DOWNLOAD) ---
                st.subheader("Base de Dados de Auditoria")
                st.markdown("A planilha abaixo contém todos os fatores de cálculo desagregados para auditoria de performance.")
                
                # Dicionário de renomeação detalhada
                nomes_colunas = {
                    'USDBRL': 'Taxa de Câmbio (USDBRL Venda)',
                    'CDI_Diario': 'Taxa CDI Diária (%)',
                    'CDI_Anualizado': 'Taxa CDI Anualizada (%)',
                    'Fed_Funds': 'Federal Funds Rate Anualizada (%)',
                    'Fator_BR': 'Fator de Capitalização BR (Base 252)',
                    'Fator_US': 'Fator de Capitalização US (Base 360)',
                    'Carry_Diario': 'Fator de Diferencial Diário (Carry)',
                    'Carry_Acumulado': 'Retorno Acumulado Carry Trade (Base 100)',
                    'Cambio_Acumulado': 'Retorno Acumulado Câmbio (Base 100)'
                }
                
                df_export = df.rename(columns=nomes_colunas)
                
                # Ordenação lógica das colunas
                ordem_colunas = [
                    'Taxa de Câmbio (USDBRL Venda)',
                    'Taxa CDI Diária (%)',
                    'Taxa CDI Anualizada (%)',
                    'Federal Funds Rate Anualizada (%)',
                    'Fator de Capitalização BR (Base 252)',
                    'Fator de Capitalização US (Base 360)',
                    'Fator de Diferencial Diário (Carry)',
                    'Retorno Acumulado Carry Trade (Base 100)',
                    'Retorno Acumulado Câmbio (Base 100)'
                ]
                
                df_export = df_export[ordem_colunas]
                
                # Exibe um preview simplificado no app
                st.dataframe(df_export.head(10).style.format(precision=4))
                
                # Botão de Download da base inteira
                csv = df_export.to_csv(index=True, sep=';', decimal=',')
                st.download_button(
                    label="📥 Baixar Planilha de Auditoria Completa (CSV PT-BR)",
                    data=csv,
                    file_name='portfel_auditoria_carry_cambio.csv',
                    mime='text/csv',
                )

            except Exception as e:
                st.error(f"Erro na simulação: {e}")
