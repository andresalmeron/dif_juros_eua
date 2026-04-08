import streamlit as st
import pandas as pd
import numpy as np
from bcb import sgs
from fredapi import Fred

# 1. Configurações Iniciais da Página
st.set_page_config(
    page_title="Dashboard Portfel: Carry Trade & Fator de Hedge", 
    layout="wide",
    initial_sidebar_state="expanded"
)

st.title("📈 Monitor Institucional: Fator de Diferencial Diário (Carry Trade)")
st.markdown("""
Esta aplicação calcula o prêmio acumulado pelo diferencial de juros entre Brasil e EUA. 
A modelagem utiliza fatores diários exatos (CDI em base 252 vs. Fed Funds em base 360), 
refletindo o padrão de mercado para *backtests* de carteiras globais com *hedge* cambial.
""")

# --- FUNÇÃO PARA CONTORNAR O LIMITE DO BCB ---
@st.cache_data(show_spinner=False)
def extrair_cdi_fatiado(data_inicio, data_fim):
    """
    Fatia a requisição ao BCB em blocos de 5 anos para burlar o limite
    de 10 anos para séries diárias do SGS. Utiliza a série 12 (CDI).
    """
    data_atual = pd.to_datetime(data_inicio)
    data_final = pd.to_datetime(data_fim)
    pedacos = []
    
    while data_atual <= data_final:
        proxima_data = min(data_atual + pd.DateOffset(years=5), data_final)
        # Série 12: Taxa de juros - CDI (anualizada, % a.a.)
        df_pedaco = sgs.get({'CDI': 12}, start=data_atual, end=proxima_data)
        pedacos.append(df_pedaco)
        data_atual = proxima_data + pd.Timedelta(days=1)
        
    return pd.concat(pedacos)
# --------------------------------------------------

# 2. Sidebar - Parâmetros do Usuário
st.sidebar.header("Parâmetros de Extração")
api_key = st.sidebar.text_input(
    "Chave API do FRED", 
    type="password", 
    help="Insira sua chave gratuita do Federal Reserve"
)

# Definindo datas padrão
data_inicio = st.sidebar.date_input("Data de Início", pd.to_datetime("2000-01-01"))
data_fim = st.sidebar.date_input("Data Final", pd.to_datetime("today"))

# 3. Botão de Execução e Processamento
if st.sidebar.button("Rodar Simulação de Fatores"):
    if not api_key:
        st.sidebar.error("A chave da API do FRED é obrigatória.")
    else:
        with st.spinner("Processando dados do BCB e FRED. Isso leva alguns segundos..."):
            try:
                # --- EXTRAÇÃO ---
                fred = Fred(api_key=api_key)
                
                # Extrai o CDI (Brasil) e DFF (EUA)
                cdi = extrair_cdi_fatiado(data_inicio, data_fim)
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                fed_funds = fed_funds.to_frame(name='Fed_Funds')

                # --- TRATAMENTO E ALINHAMENTO ---
                # Junta os dois calendários (feriados do BR e US são diferentes)
                df = pd.merge(cdi, fed_funds, left_index=True, right_index=True, how='outer')
                
                # Preenche feriados e finais de semana com a taxa do dia útil anterior
                df = df.ffill().dropna() 

                # --- MATEMÁTICA INSTITUCIONAL (FATORAÇÃO) ---
                # Fator Diário BR (Base 252 - Exponencial)
                df['Fator_BR'] = (1 + (df['CDI'] / 100)) ** (1/252)
                
                # Fator Diário US (Base 360 - Linear)
                df['Fator_US'] = 1 + ((df['Fed_Funds'] / 100) * (1/360))
                
                # Diferencial Diário (Carry)
                df['Carry_Diario_Fator'] = df['Fator_BR'] / df['Fator_US']
                df['Carry_Diario_Pct'] = (df['Carry_Diario_Fator'] - 1) * 100
                
                # Acúmulo do Fator (A "Mágica" dos Juros Compostos no Hedge)
                # O índice base começa em 100 para facilitar a visualização
                df['Carry_Acumulado (Base 100)'] = 100 * df['Carry_Diario_Fator'].cumprod()

                # --- VISUALIZAÇÃO NO DASHBOARD ---
                st.markdown("---")
                st.subheader("Desempenho do Carry Trade (Diferencial Acumulado)")
                
                # Gráfico nativo do Streamlit da curva de capitalização
                st.line_chart(df['Carry_Acumulado (Base 100)'])

                # Métricas principais
                st.markdown("### Resumo do Período")
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("Média CDI", f"{df['CDI'].mean():.2f}% a.a.")
                col2.metric("Média Fed Funds", f"{df['Fed_Funds'].mean():.2f}% a.a.")
                
                # Retorno total acumulado do spread (Opcional: Subtrai os 100 iniciais para ver só o ganho percentual)
                retorno_total_pct = df['Carry_Acumulado (Base 100)'].iloc[-1] - 100
                col3.metric("Retorno Acumulado do Hedge", f"{retorno_total_pct:.2f}%")
                
                # Anualização do retorno total (CAGR)
                anos_passados = len(df) / 252
                cagr = ((df['Carry_Acumulado (Base 100)'].iloc[-1] / 100) ** (1 / anos_passados) - 1) * 100
                col4.metric("Carry Médio Anualizado (CAGR)", f"{cagr:.2f}% a.a.")

                # --- TABELA E EXPORTAÇÃO ---
                st.markdown("---")
                st.subheader("Base de Dados Fatorada")
                
                # Mostra colunas formatadas para melhor leitura na tela
                colunas_display = ['CDI', 'Fed_Funds', 'Fator_BR', 'Fator_US', 'Carry_Diario_Pct', 'Carry_Acumulado (Base 100)']
                st.dataframe(df[colunas_display].style.format({
                    'CDI': '{:.2f}',
                    'Fed_Funds': '{:.2f}',
                    'Fator_BR': '{:.6f}',
                    'Fator_US': '{:.6f}',
                    'Carry_Diario_Pct': '{:.4f}',
                    'Carry_Acumulado (Base 100)': '{:.2f}'
                }))

                # Exportar para CSV
                csv = df.to_csv(index=True, sep=';', decimal=',')
                
                st.download_button(
                    label="📥 Fazer Download da Planilha (CSV PT-BR)",
                    data=csv,
                    file_name='portfel_hedge_fatorado.csv',
                    mime='text/csv',
                )

            except Exception as e:
                st.error(f"Erro durante a execução: {e}")
