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

# --- FUNÇÃO NOVA PARA CONTORNAR O LIMITE DO BCB ---
@st.cache_data(show_spinner=False)
def extrair_selic_fatiada(data_inicio, data_fim):
    """
    Fatia a requisição ao BCB em blocos de 5 anos para burlar o limite
    de 10 anos para séries diárias do SGS.
    """
    data_atual = pd.to_datetime(data_inicio)
    data_final = pd.to_datetime(data_fim)
    pedacos = []
    
    while data_atual <= data_final:
        # Avança 5 anos ou para na data final (o que vier primeiro)
        proxima_data = min(data_atual + pd.DateOffset(years=5), data_final)
        
        # Puxa o lote de 5 anos
        df_pedaco = sgs.get({'Selic': 432}, start=data_atual, end=proxima_data)
        pedacos.append(df_pedaco)
        
        # O próximo lote começa no dia seguinte ao término do lote atual
        data_atual = proxima_data + pd.Timedelta(days=1)
        
    # Empilha todos os pedaços em um único DataFrame
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
if st.sidebar.button("Extrair e Processar Dados"):
    if not api_key:
        st.sidebar.error("A chave da API do FRED é obrigatória.")
    else:
        with st.spinner("Conectando às bases do BCB e FRED. Isso pode levar alguns segundos devido ao loteamento de dados..."):
            try:
                # --- EXTRAÇÃO ---
                fred = Fred(api_key=api_key)
                
                # Usando a nova função que fatia os dados do BCB
                selic = extrair_selic_fatiada(data_inicio, data_fim)
                
                # Série DFF do FRED não tem essa limitação de lotes
                fed_funds = fred.get_series('DFF', observation_start=data_inicio, observation_end=data_fim)
                fed_funds = fed_funds.to_frame(name='Fed_Funds')

                # --- TRATAMENTO DE DADOS ---
                df = pd.merge(selic, fed_funds, left_index=True, right_index=True, how='outer')
                
                # Preenche finais de semana e feriados com o valor do dia útil anterior
                df = df.ffill().dropna() 
                
                # Cálculo do spread
                df['Spread (p.p.)'] = df['Selic'] - df['Fed_Funds']

                # --- VISUALIZAÇÃO NO DASHBOARD ---
                st.markdown("---")
                st.subheader(f"Resumo do Período ({data_inicio.strftime('%Y')} - {data_fim.strftime('%Y')})")
                
                col1, col2, col3 = st.columns(3)
                col1.metric("Média Selic", f"{df['Selic'].mean():.2f}%")
                col2.metric("Média Fed Funds", f"{df['Fed_Funds'].mean():.2f}%")
                col3.metric("Spread Médio", f"{df['Spread (p.p.)'].mean():.2f} p.p.")

                st.line_chart(df[['Selic', 'Fed_Funds', 'Spread (p.p.)']])

                # --- TABELA E EXPORTAÇÃO ---
                st.markdown("---")
                st.subheader("Base de Dados Completa")
                st.dataframe(df.style.format("{:.2f}"))

                csv = df.to_csv(index=True, sep=';', decimal=',')
                
                st.download_button(
                    label="📥 Fazer Download da Planilha (CSV PT-BR)",
                    data=csv,
                    file_name='portfel_spread_juros_historico.csv',
                    mime='text/csv',
                )

            except Exception as e:
                st.error(f"Erro durante a execução: {e}")
