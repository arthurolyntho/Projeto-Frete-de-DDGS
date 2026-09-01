import streamlit as st

st.set_page_config(
    page_title="Comparador FortiPro x Farelo",
    page_icon="🌽",
    layout="wide"
)

st.title("🌽 Comparador FortiPro x Farelo de Soja")
st.write("Compare o custo posto e a equivalência proteica entre os produtos.")

st.divider()

col1, col2 = st.columns(2)

# FORTIPRO
with col1:
    st.subheader("🟢 FortiPro (DDGS)")

    preco_fortipro = st.number_input(
        "Preço FOB FortiPro (R$/t)",
        min_value=0.0,
        value=1445.0,
        step=10.0
    )

    frete_fortipro = st.number_input(
        "Frete FortiPro (R$/t)",
        min_value=0.0,
        value=0.0,
        step=10.0
    )

    pb_fortipro = st.number_input(
        "Proteína Bruta FortiPro (%)",
        min_value=1.0,
        value=35.0,
        step=0.5
    )

# FARELO
with col2:
    st.subheader("🟡 Farelo de Soja")

    preco_farelo = st.number_input(
        "Preço FOB Farelo (R$/t)",
        min_value=0.0,
        value=2130.0,
        step=10.0
    )

    frete_farelo = st.number_input(
        "Frete Farelo (R$/t)",
        min_value=0.0,
        value=0.0,
        step=10.0
    )

    pb_farelo = st.number_input(
        "Proteína Bruta Farelo (%)",
        min_value=1.0,
        value=46.0,
        step=0.5
    )

# CÁLCULOS

fortipro_posto = preco_fortipro + frete_fortipro
farelo_posto = preco_farelo + frete_farelo

economia_1x1 = farelo_posto - fortipro_posto

if farelo_posto > 0:
    economia_1x1_pct = (economia_1x1 / farelo_posto) * 100
else:
    economia_1x1_pct = 0

fator_equivalencia = pb_farelo / pb_fortipro

custo_fortipro_equivalente = fortipro_posto * fator_equivalencia

economia_equivalente = farelo_posto - custo_fortipro_equivalente

if farelo_posto > 0:
    economia_equivalente_pct = (
        economia_equivalente / farelo_posto
    ) * 100
else:
    economia_equivalente_pct = 0

st.divider()

st.header("📊 Resultado")

r1, r2 = st.columns(2)

with r1:
    st.metric(
        "FortiPro posto",
        f"R$ {fortipro_posto:,.2f}/t"
    )

with r2:
    st.metric(
        "Farelo posto",
        f"R$ {farelo_posto:,.2f}/t"
    )

st.subheader("Comparação direta 1:1")

c1, c2 = st.columns(2)

c1.metric(
    "Economia por tonelada",
    f"R$ {economia_1x1:,.2f}"
)

c2.metric(
    "Economia percentual",
    f"{economia_1x1_pct:.2f}%"
)

st.divider()

st.subheader("🧪 Equivalência por Proteína Bruta")

st.write(
    f"Para fornecer a mesma quantidade de PB de **1 tonelada de farelo "
    f"{pb_farelo:.1f}%**, seriam necessários aproximadamente "
    f"**{fator_equivalencia:.3f} t de FortiPro {pb_fortipro:.1f}%**."
)

e1, e2, e3 = st.columns(3)

e1.metric(
    "FortiPro necessário",
    f"{fator_equivalencia:.3f} t"
)

e2.metric(
    "Custo do FortiPro equivalente",
    f"R$ {custo_fortipro_equivalente:,.2f}"
)

e3.metric(
    "Economia equivalente",
    f"R$ {economia_equivalente:,.2f}",
    f"{economia_equivalente_pct:.2f}%"
)

st.caption(
    "A equivalência considera somente Proteína Bruta (PB) e não representa "
    "uma formulação nutricional completa."
)
