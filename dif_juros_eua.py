import streamlit as st
import pandas as pd
from bcb import sgs
from fredapi import Fred

# 1. Configurações Iniciais da Página
st.set_page_config(
    page_title="Dashboard Portfel: Spread BR vs EUA", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 Monitor de Diferencial de Juros: Brasil vs EUA")
st.markdown("""
Esta aplicação extrai e consolida as séries temporais da **Meta Selic (SGS/BCB)** e da **Daily Federal Funds Rate (FRED)**, 
calculando o spread histórico diário para análises de prêmio de risco cambial e *carry trade*.
""")

# 2. Sidebar - Parâmetros do Usuário
st.sidebar.header("Parâmetros de Extração")
api_key = st.sidebar.text_input(
    "Chave API do FRED", 
    type="password", 
    help="Insira sua chave gratuita do Federal Reserve (https://fred.stlouisfed.org/docs/api/api_key.html)"
)

# Definindo datas padrão (do ano 2000 até hoje, capturando a era do Tripé Macroeconômico)
data_inicio = st.sidebar.date_input("Data de Início", pd.to_datetime("2000-01-01"))
data_fim = st.sidebar.date_input("Data Final", pd.to_datetime("today"))

# 3. Botão de Execução e Processamento
if st.sidebar.button("Extrair e Processar Dados"):
    if not api_key:
        st.sidebar.error("A chave da API do FRED é obrigatória.")
    else:
        with st.spinner("Conectando às bases do BCB e FRED..."):
            try:
                # --- EXTRAÇÃO ---
                fred = Fred(api_key=api_key)
                
                # Série 432 do BCB = Meta Selic definida pelo Copom
                selic = sgs.get({'Selic': 432}, start=data_inicio, end=data_fim)
                
                # Série DFF do FRED = Daily Effective Federal Funds Rate
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                fed_funds = fed_funds.to_frame(name='Fed_Funds')

                # --- TRATAMENTO DE DADOS ---
                # Merge 'outer' para garantir que não perderemos dias onde apenas um dos mercados operou
                df = pd.merge(selic, fed_funds, left_index=True, right_index=True, how='outer')
                
                # O método ffill() (forward fill) carrega a última taxa válida para os finais de semana/feriados
                df = df.ffill().dropna() 
                
                # Cálculo do spread em pontos percentuais
                df['Spread (p.p.)'] = df['Selic'] - df['Fed_Funds']

                # --- VISUALIZAÇÃO NO DASHBOARD ---
                st.markdown("---")
                st.subheader(f"Resumo do Período ({data_inicio.strftime('%Y')} - {data_fim.strftime('%Y')})")
                
                # Métricas principais
                col1, col2, col3 = st.columns(3)
                col1.metric("Média Selic", f"{df['Selic'].mean():.2f}%")
                col2.metric("Média Fed Funds", f"{df['Fed_Funds'].mean():.2f}%")
                col3.metric("Spread Médio", f"{df['Spread (p.p.)'].mean():.2f} p.p.")

                # Gráfico nativo do Streamlit
                st.line_chart(df[['Selic', 'Fed_Funds', 'Spread (p.p.)']])

                # --- TABELA E EXPORTAÇÃO ---
                st.markdown("---")
                st.subheader("Base de Dados Completa")
                
                # Exibe o dataframe interativo na tela
                st.dataframe(df.style.format("{:.2f}"))

                # Preparar o CSV (padrão PT-BR para abrir direto no Excel sem quebrar)
                csv = df.to_csv(index=True, sep=';', decimal=',')
                
                st.download_button(
                    label="📥 Fazer Download da Planilha (CSV PT-BR)",
                    data=csv,
                    file_name='portfel_spread_juros_historico.csv',
                    mime='text/csv',
                )

            except Exception as e:
                st.error(f"Erro durante a execução: {e}")
