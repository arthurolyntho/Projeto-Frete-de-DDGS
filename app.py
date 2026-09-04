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
# CAPACIDADE AUTOMÁTICA POR EIXOS
# =========================================================

CAPACIDADE_EIXOS = {
    2: 10.0,
    3: 14.0,
    4: 17.0,
    5: 26.0,
    6: 31.0,
    7: 36.0,
    8: 40.0,
    9: 49.0
}


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
# BUSCA DE CIDADES
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
# CLICA EM BOTÃO
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
# COTAÇÃO MAISFRETE
# =========================================================

def cotar(
    origem,
    uf_o,
    destino,
    uf_d,
    eixos,
    peso,
    margem_empresa,
    icms,
    margem_seguranca
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
                (
                    By.ID,
                    "input-0"
                )
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
        # PREENCHE EIXOS / PESO / MARGEM / ICMS
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
                    str(margem_empresa)
                    .replace(".", ","),

                "prIcms":
                    (
                        str(icms)
                        .replace(".", ",")
                        if icms > 0
                        else ""
                    ),

                "vlPesoTonelada":
                    f"{float(peso):.2f}"
                    .replace(".", ",")
            }
        )

        # -------------------------------------------------
        # CALCULAR
        # -------------------------------------------------

        if not clicar(
            driver,
            "calcular"
        ):
            raise RuntimeError(
                "Botão Calcular não encontrado."
            )

        # -------------------------------------------------
        # CAPTURA GRANEL SÓLIDO
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
                            texto.startsWith(
                                "Granel Sólido"
                            ) &&
                            (
                                texto.match(/R\$/g)
                                || []
                            ).length >= 7
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
                    valores.length < 7
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

        # -------------------------------------------------
        # VALORES MAISFRETE
        # -------------------------------------------------

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

        pedagio_total = br_to_float(
            valores[6]
        )

        # -------------------------------------------------
        # PEDÁGIO POR TONELADA
        # -------------------------------------------------

        pedagio_t = (
            pedagio_total /
            float(peso)
            if peso
            else 0.0
        )

        # -------------------------------------------------
        # FRETE + PEDÁGIO
        # -------------------------------------------------

        frete_base_t = (
            frete_empresa_t +
            pedagio_t
        )

        # -------------------------------------------------
        # MARGEM DE SEGURANÇA
        # -------------------------------------------------

        margem_seguranca_t = (
            frete_base_t *
            (
                margem_seguranca /
                100
            )
        )

        # -------------------------------------------------
        # FRETE FINAL
        # -------------------------------------------------

        frete_final_t = (
            frete_base_t +
            margem_seguranca_t
        )

        frete_final_carga = (
            frete_final_t *
            float(peso)
        )

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
                frete_empresa_t,

            "pedagio_total":
                pedagio_total,

            "pedagio_t":
                pedagio_t,

            "frete_base_t":
                frete_base_t,

            "margem_seguranca_pct":
                margem_seguranca,

            "margem_seguranca_t":
                margem_seguranca_t,

            "frete_final_t":
                frete_final_t,

            "frete_final_carga":
                frete_final_carga,

            "icms":
                icms
        }

    finally:

        driver.quit()


# =========================================================
# TÍTULO / ABAS
# =========================================================

st.title(
    "FortiPro | Formação de preço"
)

tab1, tab2, tab3 = st.tabs(
    [
        "V1 • Fiscal",
        "V2 • Logística",
        "V3 • Resultado"
    ]
)


# =========================================================
# V1 — FISCAL
# =========================================================

with tab1:

    st.subheader(
        "Dados fiscais do FortiPro"
    )

    st.caption(
        "Dados conforme a NF enviada pela Inpasa."
    )

    f1, f2, f3, f4 = st.columns(4)

    f1.metric(
        "NCM",
        "2302.10.00"
    )

    f2.metric(
        "CST",
        "090"
    )

    f3.metric(
        "IPI",
        "0%"
    )

    f4.metric(
        "PIS/Cofins",
        "Suspensos*"
    )

    st.caption(
        "* Conforme enquadramento legal aplicável às vendas abrangidas pela suspensão."
    )

    st.divider()

    forti_fob = st.number_input(
        "Preço FOB FortiPro (R$/t)",
        min_value=0.0,
        value=1445.0,
        step=10.0
    )

    st.session_state[
        "forti_fob"
    ] = forti_fob

    st.info(
        "O ICMS será informado na V2 porque depende da operação e será aplicado na cotação do MaisFrete."
    )


# =========================================================
# V2 — LOGÍSTICA
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

    # -----------------------------------------------------
    # EIXOS AUTOMÁTICOS
    # -----------------------------------------------------

    eixos = st.selectbox(
        "Quantidade de eixos",
        options=[
            2,
            3,
            4,
            5,
            6,
            7,
            8,
            9
        ],
        index=5
    )

    peso = CAPACIDADE_EIXOS[
        eixos
    ]

    st.info(
        f"Capacidade automática considerada: "
        f"{peso:.0f} toneladas para {eixos} eixos."
    )

    # -----------------------------------------------------
    # MARGEM / ICMS / SEGURANÇA
    # -----------------------------------------------------

    a, b, c = st.columns(3)

    with a:

        margem_empresa = st.number_input(
            "Margem empresa MaisFrete (%)",
            min_value=0.0,
            max_value=100.0,
            value=25.0,
            step=1.0
        )

    with b:

        icms = st.number_input(
            "ICMS (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help=(
                "Informe a alíquota aplicável "
                "à operação. Deixe 0 quando "
                "não houver ICMS a informar."
            )
        )

    with c:

        margem_seguranca = st.number_input(
            "Margem de segurança (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0
        )

    # -----------------------------------------------------
    # BOTÃO
    # -----------------------------------------------------

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
                    margem_empresa,
                    icms,
                    margem_seguranca
                )

                st.session_state[
                    "resultado_logistica"
                ] = resultado

                st.session_state[
                    "frete_final_t"
                ] = resultado[
                    "frete_final_t"
                ]

            except Exception as erro:

                st.error(
                    "Falha na automação do MaisFrete."
                )

                st.exception(
                    erro
                )

    resultado = st.session_state.get(
        "resultado_logistica"
    )

    if resultado:

        st.success(
            f'{resultado["origem"]} → '
            f'{resultado["destino"]}'
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

        y1, y2, y3 = st.columns(3)

        y1.metric(
            "Pedágio",
            br_money(
                resultado[
                    "pedagio_total"
                ]
            )
        )

        y2.metric(
            "Pedágio / t",
            br_money(
                resultado[
                    "pedagio_t"
                ]
            )
        )

        y3.metric(
            "Frete + pedágio / t",
            br_money(
                resultado[
                    "frete_base_t"
                ]
            )
        )

        z1, z2, z3 = st.columns(3)

        z1.metric(
            "Margem segurança / t",
            br_money(
                resultado[
                    "margem_seguranca_t"
                ]
            )
        )

        z2.metric(
            "Frete final / t",
            br_money(
                resultado[
                    "frete_final_t"
                ]
            )
        )

        z3.metric(
            "Frete final da carga",
            br_money(
                resultado[
                    "frete_final_carga"
                ]
            )
        )

        st.caption(
            f"{eixos} eixos • "
            f"{peso:.0f} t • "
            f"margem MaisFrete {margem_empresa:.0f}% • "
            f"ICMS {icms:.1f}% • "
            f"margem segurança {margem_seguranca:.1f}%"
        )


# =========================================================
# V3 — RESULTADO
# =========================================================

with tab3:

    st.subheader(
        "FortiPro posto na propriedade"
    )

    forti_fob_final = st.session_state.get(
        "forti_fob",
        1445.0
    )

    frete_final_t = st.session_state.get(
        "frete_final_t"
    )

    if frete_final_t is None:

        st.warning(
            "Calcule primeiro a logística na V2 para obter o preço posto na propriedade."
        )

    else:

        forti_posto = (
            forti_fob_final +
            frete_final_t
        )

        r1, r2, r3 = st.columns(3)

        r1.metric(
            "FOB FortiPro",
            br_money(
                forti_fob_final
            )
        )

        r2.metric(
            "Logística / t",
            br_money(
                frete_final_t
            )
        )

        r3.metric(
            "FortiPro posto",
            br_money(
                forti_posto
            )
        )

        st.success(
            "Preço estimado do FortiPro entregue "
            "na propriedade: "
            +
            br_money(
                forti_posto
            )
            +
            "/t."
        )

        st.caption(
            "FortiPro posto = preço FOB + frete logístico final por tonelada."
        )
