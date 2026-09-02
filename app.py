import os
import re
import unicodedata

import streamlit as st

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC


URL = "https://consulta.maisfrete.com.br/exe_consulta_frete_minimo.php"


st.set_page_config(
    page_title="FortiPro | Preço Posto",
    page_icon="🚚",
    layout="wide"
)


# =========================================================
# FUNÇÕES AUXILIARES
# =========================================================

def br_money(v):
    if v is None:
        return "—"

    return (
        f"R$ {v:,.2f}"
        .replace(",", "X")
        .replace(".", ",")
        .replace("X", ".")
    )


def br_to_float(txt):
    if not txt:
        return None

    txt = (
        txt.replace("R$", "")
        .strip()
        .replace(".", "")
        .replace(",", ".")
    )

    m = re.search(r"-?\d+(?:\.\d+)?", txt)

    return float(m.group()) if m else None


def normalizar(s):
    return "".join(
        c
        for c in unicodedata.normalize("NFD", s)
        if unicodedata.category(c) != "Mn"
    ).lower().strip()


# =========================================================
# SELENIUM / CHROMIUM
# =========================================================

def get_driver():

    opts = Options()

    argumentos = [
        "--headless=new",
        "--no-sandbox",
        "--disable-dev-shm-usage",
        "--disable-gpu",
        "--window-size=1440,1200"
    ]

    for arg in argumentos:
        opts.add_argument(arg)

    for caminho in [
        "/usr/bin/chromium",
        "/usr/bin/chromium-browser"
    ]:
        if os.path.exists(caminho):
            opts.binary_location = caminho
            break

    for caminho in [
        "/usr/bin/chromedriver",
        "/usr/lib/chromium/chromedriver"
    ]:
        if os.path.exists(caminho):
            return webdriver.Chrome(
                service=Service(caminho),
                options=opts
            )

    return webdriver.Chrome(options=opts)


# =========================================================
# BUSCA DE CIDADES NO MAISFRETE
# =========================================================

def selecionar_cidade(
    driver,
    input_id,
    hidden_id,
    busca,
    uf
):

    js = r"""
    const done = arguments[arguments.length - 1];

    const inputId = arguments[0];
    const hiddenId = arguments[1];
    const busca = arguments[2];
    const uf = arguments[3];

    const url =
        "/lib/jaguar/AjaxIframe.php" +
        "?c=Cidade" +
        "&a=obterCidadesAutoComplete" +
        "&p%5BdsItem%5D=" +
        encodeURIComponent(busca);

    fetch(
        url,
        {
            credentials: "same-origin",
            headers: {
                "X-Requested-With": "XMLHttpRequest"
            }
        }
    )
    .then(r => r.json())
    .then(dados => {

        const cidade = dados.find(
            item =>
                (item.description || "")
                .endsWith("/ " + uf)
        );

        if (!cidade) {
            done({
                ok: false,
                dados: dados
            });
            return;
        }

        const campoVisivel =
            document.getElementById(inputId);

        const campoOculto =
            document.getElementById(hiddenId);

        campoVisivel.value =
            cidade.description;

        campoOculto.value =
            cidade.value;

        campoVisivel.dispatchEvent(
            new Event("input", {bubbles: true})
        );

        campoVisivel.dispatchEvent(
            new Event("change", {bubbles: true})
        );

        campoOculto.dispatchEvent(
            new Event("change", {bubbles: true})
        );

        done({
            ok: true,
            cidade: cidade
        });
    })
    .catch(
        erro =>
            done({
                ok: false,
                erro: String(erro)
            })
    );
    """

    return driver.execute_async_script(
        js,
        input_id,
        hidden_id,
        busca,
        uf
    )


# =========================================================
# CLICA EM BOTÃO PELO TEXTO
# =========================================================

def clicar(driver, texto):

    return driver.execute_script(
        """
        const texto =
            arguments[0]
            .toLowerCase();

        const elementos =
            [
                ...document.querySelectorAll(
                    "button," +
                    "input[type=button]," +
                    "input[type=submit]"
                )
            ];

        const botao =
            elementos.find(
                el =>
                    (
                        el.innerText ||
                        el.value ||
                        ""
                    )
                    .trim()
                    .toLowerCase()
                    .includes(texto)
            );

        if (!botao) {
            return false;
        }

        botao.click();

        return true;
        """,
        texto
    )


# =========================================================
# COTAÇÃO COMPLETA
# =========================================================

def cotar(
    origem,
    uf_o,
    destino,
    uf_d,
    eixos,
    peso,
    margem
):

    driver = get_driver()

    try:

        driver.get(URL)

        wait = WebDriverWait(
            driver,
            40
        )

        wait.until(
            EC.presence_of_element_located(
                (By.ID, "input-0")
            )
        )

        # -------------------------------------------------
        # ORIGEM
        # -------------------------------------------------

        origem_resultado = selecionar_cidade(
            driver,
            "input-0",
            "f_cd_cidade_origem",
            normalizar(origem),
            uf_o.upper()
        )

        if not origem_resultado.get("ok"):
            raise RuntimeError(
                "Origem não encontrada."
            )

        # -------------------------------------------------
        # DESTINO
        # -------------------------------------------------

        destino_resultado = selecionar_cidade(
            driver,
            "input-1",
            "f_cd_cidade_destino",
            normalizar(destino),
            uf_d.upper()
        )

        if not destino_resultado.get("ok"):
            raise RuntimeError(
                "Destino não encontrado."
            )

        # -------------------------------------------------
        # ROTEIRIZAÇÃO
        # -------------------------------------------------

        if not clicar(
            driver,
            "roteirizar"
        ):
            raise RuntimeError(
                "Botão Roteirizar não encontrado."
            )

        wait.until(
            lambda d:
                (
                    d.find_element(
                        By.ID,
                        "qtKmRodado"
                    )
                    .get_attribute("value")
                    or ""
                ).strip()
        )

        km_texto = (
            driver
            .find_element(
                By.ID,
                "qtKmRodado"
            )
            .get_attribute("value")
            .strip()
        )

        # -------------------------------------------------
        # PREENCHE EIXOS / PESO / MARGEM
        # -------------------------------------------------

        driver.execute_script(
            """
            const valores = arguments[0];

            Object.entries(valores)
            .forEach(([id, valor]) => {

                const campo =
                    document.getElementById(id);

                if (!campo) {
                    return;
                }

                campo.value = valor;

                campo.dispatchEvent(
                    new Event(
                        "input",
                        {bubbles: true}
                    )
                );

                campo.dispatchEvent(
                    new Event(
                        "change",
                        {bubbles: true}
                    )
                );
            });
            """,
            {
                "qtEixos":
                    str(eixos),

                "prMargemTransportadora":
                    str(margem)
                    .replace(".", ","),

                "vlPesoTonelada":
                    f"{float(peso):.2f}"
                    .replace(".", ",")
            }
        )

        # -------------------------------------------------
        # CLICA CALCULAR
        # -------------------------------------------------

        if not clicar(
            driver,
            "calcular"
        ):
            raise RuntimeError(
                "Botão Calcular não encontrado."
            )

        # -------------------------------------------------
        # ESPERA E CAPTURA OS VALORES DE GRANEL SÓLIDO
        # -------------------------------------------------

        def valores_granel(d):

            return d.execute_script(
                r"""
                const linhas =
                    [...document.querySelectorAll("tr")];

                const linha =
                    linhas.find(l => {

                        const texto =
                            (l.innerText || "").trim();

                        return (
                            texto.startsWith("Granel Sólido") &&
                            (texto.match(/R\$/g) || []).length >= 6
                        );
                    });

                if (!linha) {
                    return null;
                }

                const texto =
                    (linha.innerText || "").trim();

                const valores =
                    texto.match(
                        /R\$\s*[0-9\.]+(?:,[0-9]+)?/g
                    );

                if (
                    !valores ||
                    valores.length < 6
                ) {
                    return null;
                }

                return {
                    texto: texto,
                    valores: valores
                };
                """
            )

        dados_granel = wait.until(
            valores_granel
        )

        valores = dados_granel[
            "valores"
        ]

        # Ordem esperada:
        # 0 = KM/eixo
        # 1 = carga/descarga
        # 2 = frete mínimo total
        # 3 = frete mínimo por tonelada
        # 4 = frete empresa total
        # 5 = frete empresa por tonelada

        frete_minimo = br_to_float(
            valores[2]
        )

        frete_minimo_t = br_to_float(
            valores[3]
        )

        frete_empresa = br_to_float(
            valores[4]
        )

        frete_empresa_t = br_to_float(
            valores[5]
        )

        # -------------------------------------------------
        # RESULTADO
        # -------------------------------------------------

        return {
            "origem":
                origem_resultado[
                    "cidade"
                ][
                    "description"
                ],

            "destino":
                destino_resultado[
                    "cidade"
                ][
                    "description"
                ],

            "km":
                br_to_float(
                    km_texto
                ),

            "frete_min":
                frete_minimo,

            "frete_min_t":
                frete_minimo_t,

            "frete_emp":
                frete_empresa,

            "frete_emp_t":
                frete_empresa_t
        }

    finally:
        driver.quit()


# =========================================================
# INTERFACE
# =========================================================

st.title(
    "FortiPro | Formação de preço"
)


tab1, tab2, tab3 = st.tabs(
    [
        "V1 • Produto",
        "V2 • Logística",
        "V3 • Fiscal"
    ]
)


# =========================================================
# V1
# =========================================================

with tab1:

    st.subheader(
        "Comparativo FortiPro x Farelo de Soja"
    )

    c1, c2 = st.columns(2)

    with c1:

        forti = st.number_input(
            "FOB FortiPro (R$/t)",
            value=1445.0,
            step=10.0
        )

        pb_f = st.number_input(
            "PB FortiPro (%)",
            value=35.0,
            step=0.5
        )

    with c2:

        soja = st.number_input(
            "FOB Farelo (R$/t)",
            value=2130.0,
            step=10.0
        )

        pb_s = st.number_input(
            "PB Farelo (%)",
            value=46.0,
            step=0.5
        )

    frete = st.session_state.get(
        "frete_emp_t",
        0.0
    )

    posto = forti + frete

    economia = soja - posto

    economia_pct = (
        economia / soja * 100
        if soja
        else 0
    )

    fator_pb = (
        pb_s / pb_f
        if pb_f
        else 0
    )

    equivalente_pb = (
        posto * fator_pb
    )

    a, b, c = st.columns(3)

    a.metric(
        "FortiPro posto",
        br_money(posto)
    )

    b.metric(
        "Economia 1:1",
        br_money(economia),
        f"{economia_pct:.1f}%"
    )

    c.metric(
        "Equivalente em PB",
        br_money(
            equivalente_pb
        )
    )

    if frete:

        st.success(
            "Frete calculado na V2 aplicado automaticamente: "
            +
            br_money(frete)
            +
            "/t"
        )

    st.caption(
        "Equivalência por proteína bruta é uma referência econômica simplificada e não substitui formulação nutricional."
    )


# =========================================================
# V2
# =========================================================

with tab2:

    st.subheader(
        "Cotação automática no MaisFrete"
    )

    c1, c2 = st.columns(2)

    with c1:

        origem = st.text_input(
            "Cidade de origem",
            "Uberlândia"
        )

        uf_o = st.text_input(
            "UF origem",
            "MG",
            max_chars=2
        ).upper()

    with c2:

        destino = st.text_input(
            "Cidade de destino",
            "Viçosa"
        )

        uf_d = st.text_input(
            "UF destino",
            "MG",
            max_chars=2
        ).upper()

    a, b, c = st.columns(3)

    with a:

        eixos = st.selectbox(
            "Eixos",
            [3, 4, 5, 6, 7, 9],
            index=4
        )

    with b:

        peso = st.number_input(
            "Peso (t)",
            min_value=1.0,
            value=36.0,
            step=1.0
        )

    with c:

        margem = st.number_input(
            "Margem (%)",
            min_value=0.0,
            max_value=100.0,
            value=25.0,
            step=1.0
        )

    if st.button(
        "Calcular logística",
        type="primary",
        use_container_width=True
    ):

        with st.spinner(
            "Consultando MaisFrete..."
        ):

            try:

                resultado = cotar(
                    origem,
                    uf_o,
                    destino,
                    uf_d,
                    eixos,
                    peso,
                    margem
                )

                st.session_state[
                    "resultado"
                ] = resultado

                st.session_state[
                    "frete_emp_t"
                ] = resultado[
                    "frete_emp_t"
                ]

            except Exception as erro:

                st.error(
                    "Falha na automação do MaisFrete."
                )

                st.exception(
                    erro
                )

    resultado = st.session_state.get(
        "resultado"
    )

    if resultado:

        st.success(
            f'{resultado["origem"]} → {resultado["destino"]}'
        )

        x1, x2, x3, x4 = st.columns(4)

        x1.metric(
            "Distância",
            f'{resultado["km"]:.0f} km'
        )

        x2.metric(
            "Frete mínimo",
            br_money(
                resultado[
                    "frete_min"
                ]
            )
        )

        x3.metric(
            "Frete empresa",
            br_money(
                resultado[
                    "frete_emp"
                ]
            )
        )

        x4.metric(
            "Frete empresa / t",
            br_money(
                resultado[
                    "frete_emp_t"
                ]
            )
        )

        st.caption(
            f"{eixos} eixos • {peso:.0f} t • margem {margem:.0f}% • Granel Sólido"
        )


# =========================================================
# V3
# =========================================================

with tab3:

    st.info(
        "V3 entra depois da confirmação do NCM e do tratamento fiscal real da NF do FortiPro."
    )
