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

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        txt
    )

    return float(
        m.group()
    ) if m else None


def normalizar(s):
    return "".join(
        c
        for c in unicodedata.normalize(
            "NFD",
            s
        )
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

    return webdriver.Chrome(
        options=opts
    )


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
            document.getElementById(
                inputId
            );

        const campoOculto =
            document.getElementById(
                hiddenId
            );

        campoVisivel.value =
            cidade.description;

        campoOculto.value =
            cidade.value;

        campoVisivel.dispatchEvent(
            new Event(
                "input",
                {bubbles: true}
            )
        );

        campoVisivel.dispatchEvent(
            new Event(
                "change",
                {bubbles: true}
            )
        );

        campoOculto.dispatchEvent(
            new Event(
                "change",
                {bubbles: true}
            )
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

def clicar(
    driver,
    texto
):

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

        driver.get(
            URL
        )

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

        if not origem_resultado.get(
            "ok"
        ):
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

        if not destino_resultado.get(
            "ok"
        ):
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
                    .get_attribute(
                        "value"
                    )
                    or ""
                ).strip()
        )

        km_texto = (
            driver
            .find_element(
                By.ID,
                "qtKmRodado"
            )
            .get_attribute(
                "value"
            )
            .strip()
        )

        # -------------------------------------------------
        # EIXOS / PESO / MARGEM EMPRESA
        # -------------------------------------------------

        driver.execute_script(
            """
            const valores =
                arguments[0];

            Object.entries(
                valores
            )
            .forEach(
                ([id, valor]) => {

                    const campo =
                        document
                        .getElementById(id);

                    if (!campo) {
                        return;
                    }

                    campo.value =
                        valor;

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
                }
            );
            """,
            {
                "qtEixos":
                    str(eixos),

                "prMargemTransportadora":
                    str(
                        margem_empresa
                    ).replace(
                        ".",
                        ","
                    ),

                "vlPesoTonelada":
                    f"{float(peso):.2f}"
                    .replace(
                        ".",
                        ","
                    )
            }
        )

        # -------------------------------------------------
        # CALCULA
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
                    [
                        ...document
                        .querySelectorAll(
                            "tr"
                        )
                    ];

                const linha =
                    linhas.find(
                        l => {

                            const texto =
                                (
                                    l.innerText ||
                                    ""
                                )
                                .trim();

                            return (
                                texto.startsWith(
                                    "Granel Sólido"
                                )
                                &&
                                (
                                    texto.match(
                                        /R\$/g
                                    )
                                    ||
                                    []
                                ).length >= 7
                            );
                        }
                    );

                if (!linha) {
                    return null;
                }

                const texto =
                    (
                        linha.innerText ||
                        ""
                    )
                    .trim();

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
        # DADOS DO MAISFRETE
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
        # PEDÁGIO
        # -------------------------------------------------

        pedagio_t = (
            pedagio_total /
            float(peso)
            if peso
            else 0.0
        )

        # Frete empresa + pedágio
        frete_base_t = (
            frete_empresa_t +
            pedagio_t
        )

        frete_base_total = (
            frete_empresa +
            pedagio_total
        )

        # -------------------------------------------------
        # ICMS MANUAL
        # -------------------------------------------------

        valor_icms_t = (
            frete_base_t *
            (icms / 100)
        )

        # -------------------------------------------------
        # MARGEM DE SEGURANÇA
        # -------------------------------------------------

        valor_margem_seguranca_t = (
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
            valor_icms_t +
            valor_margem_seguranca_t
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

            "icms_pct":
                icms,

            "icms_t":
                valor_icms_t,

            "margem_seguranca_pct":
                margem_seguranca,

            "margem_seguranca_t":
                valor_margem_seguranca_t,

            "frete_final_t":
                frete_final_t,

            "frete_final_carga":
                frete_final_carga
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
# V1 — PRODUTO
# =========================================================

with tab1:

    st.subheader(
        "Comparativo econômico"
    )

    c1, c2 = st.columns(
        2
    )

    # -----------------------------------------------------
    # FORTIPRO
    # -----------------------------------------------------

    with c1:

        st.markdown(
            "### FortiPro"
        )

        forti_fob = st.number_input(
            "FOB FortiPro (R$/t)",
            value=1445.0,
            step=10.0
        )

        pb_f = st.number_input(
            "Proteína bruta FortiPro (%)",
            value=35.0,
            step=0.5
        )

        pndr_f = st.number_input(
            "PNDR FortiPro (% da PB)",
            min_value=0.0,
            max_value=100.0,
            value=55.0,
            step=1.0
        )

    # -----------------------------------------------------
    # SOJA
    # -----------------------------------------------------

    with c2:

        st.markdown(
            "### Farelo de soja"
        )

        soja_posto = st.number_input(
            "Farelo de soja posto (R$/t)",
            value=2130.0,
            step=10.0
        )

        pb_s = st.number_input(
            "Proteína bruta farelo (%)",
            value=46.0,
            step=0.5
        )

        pndr_s = st.number_input(
            "PNDR farelo (% da PB)",
            min_value=0.0,
            max_value=100.0,
            value=35.0,
            step=1.0
        )

    # -----------------------------------------------------
    # FRETE VINDO DA V2
    # -----------------------------------------------------

    frete_final_t = (
        st.session_state.get(
            "frete_final_t",
            0.0
        )
    )

    # -----------------------------------------------------
    # PREÇO POSTO FORTIPRO
    # -----------------------------------------------------

    forti_posto = (
        forti_fob +
        frete_final_t
    )

    # -----------------------------------------------------
    # CUSTO POR KG DE PB
    #
    # 35% PB = 350 kg PB / tonelada
    # preço / 350 = R$/kg PB
    # -----------------------------------------------------

    kg_pb_f = (
        1000 *
        pb_f /
        100
    )

    kg_pb_s = (
        1000 *
        pb_s /
        100
    )

    custo_pb_f = (
        forti_posto /
        kg_pb_f
        if kg_pb_f
        else 0
    )

    custo_pb_s = (
        soja_posto /
        kg_pb_s
        if kg_pb_s
        else 0
    )

    # -----------------------------------------------------
    # DIFERENÇA % NO CUSTO DA PB
    # -----------------------------------------------------

    diferenca_pb_pct = (
        (
            custo_pb_f /
            custo_pb_s
            -
            1
        )
        *
        100
        if custo_pb_s
        else 0
    )

    # -----------------------------------------------------
    # PREÇO TETO DDG
    #
    # Valor em que o R$/kg PB do DDG
    # empata com o farelo de soja.
    # -----------------------------------------------------

    preco_teto_ddg_posto = (
        custo_pb_s *
        kg_pb_f
    )

    preco_teto_ddg_fob = (
        preco_teto_ddg_posto -
        frete_final_t
    )

    # -----------------------------------------------------
    # RELAÇÃO DE PREÇO DDG / SOJA
    # -----------------------------------------------------

    relacao_ddg_soja = (
        forti_posto /
        soja_posto *
        100
        if soja_posto
        else 0
    )

    # -----------------------------------------------------
    # EQUIVALÊNCIA POR PB
    # -----------------------------------------------------

    fator_equivalencia_pb = (
        pb_s /
        pb_f
        if pb_f
        else 0
    )

    custo_equivalente_pb = (
        forti_posto *
        fator_equivalencia_pb
    )

    # -----------------------------------------------------
    # PNDR
    # -----------------------------------------------------

    kg_pndr_f = (
        kg_pb_f *
        pndr_f /
        100
    )

    kg_pndr_s = (
        kg_pb_s *
        pndr_s /
        100
    )

    custo_pndr_f = (
        forti_posto /
        kg_pndr_f
        if kg_pndr_f
        else 0
    )

    custo_pndr_s = (
        soja_posto /
        kg_pndr_s
        if kg_pndr_s
        else 0
    )

    # =====================================================
    # RESULTADOS PRINCIPAIS
    # =====================================================

    st.divider()

    st.markdown(
        "### Resultado principal"
    )

    r1, r2, r3 = st.columns(
        3
    )

    r1.metric(
        "FortiPro posto",
        br_money(
            forti_posto
        )
    )

    r2.metric(
        "Custo/kg PB FortiPro",
        br_money(
            custo_pb_f
        )
    )

    r3.metric(
        "Custo/kg PB soja",
        br_money(
            custo_pb_s
        )
    )

    # -----------------------------------------------------
    # DIFERENÇA
    # -----------------------------------------------------

    if diferenca_pb_pct < 0:

        st.success(
            f"FortiPro está "
            f"{abs(diferenca_pb_pct):.1f}% "
            "mais barato por kg de proteína bruta que o farelo de soja."
        )

    elif diferenca_pb_pct > 0:

        st.warning(
            f"FortiPro está "
            f"{diferenca_pb_pct:.1f}% "
            "mais caro por kg de proteína bruta que o farelo de soja."
        )

    else:

        st.info(
            "Os dois produtos estão empatados em custo por kg de proteína bruta."
        )

    # =====================================================
    # INDICADORES
    # =====================================================

    st.markdown(
        "### Indicadores econômicos"
    )

    i1, i2, i3 = st.columns(
        3
    )

    i1.metric(
        "Preço-teto DDG posto",
        br_money(
            preco_teto_ddg_posto
        )
    )

    i2.metric(
        "Relação DDG / soja",
        f"{relacao_ddg_soja:.1f}%"
    )

    i3.metric(
        "Equivalente PB",
        br_money(
            custo_equivalente_pb
        )
    )

    st.caption(
        "Preço-teto DDG: preço máximo do FortiPro posto em que o custo por kg de proteína bruta empata com o farelo de soja."
    )

    st.caption(
        "Relação DDG/soja: preço posto do FortiPro dividido pelo preço posto do farelo de soja."
    )

    st.caption(
        f"Equivalência PB: 1 t de farelo com {pb_s:.1f}% PB equivale, apenas em proteína bruta, a aproximadamente "
        f"{fator_equivalencia_pb:.2f} t de FortiPro com {pb_f:.1f}% PB. "
        f"Por isso: {fator_equivalencia_pb:.2f} × {br_money(forti_posto)} = {br_money(custo_equivalente_pb)}."
    )

    st.caption(
        "A equivalência por proteína bruta é uma comparação econômica simplificada e não representa substituição nutricional direta."
    )

    # =====================================================
    # PREÇO TETO FOB
    # =====================================================

    st.info(
        "Com o frete atual, o FOB máximo estimado do FortiPro para empatar com a soja em custo/kg PB seria "
        +
        br_money(
            preco_teto_ddg_fob
        )
        +
        "/t."
    )

    # =====================================================
    # PNDR
    # =====================================================

    with st.expander(
        "Análise complementar de PNDR"
    ):

        p1, p2 = st.columns(
            2
        )

        p1.metric(
            "Custo/kg PNDR FortiPro",
            br_money(
                custo_pndr_f
            )
        )

        p2.metric(
            "Custo/kg PNDR soja",
            br_money(
                custo_pndr_s
            )
        )

        st.caption(
            "PNDR = proteína não degradável no rúmen. O cálculo considera a porcentagem de PNDR informada aplicada sobre a proteína bruta do produto."
        )

    # =====================================================
    # FRETE APLICADO
    # =====================================================

    if frete_final_t:

        st.success(
            "Frete logístico da V2 aplicado ao FortiPro: "
            +
            br_money(
                frete_final_t
            )
            +
            "/t."
        )

    else:

        st.info(
            "Calcule a logística na V2 para adicionar automaticamente o frete ao preço posto do FortiPro."
        )


# =========================================================
# V2 — LOGÍSTICA
# =========================================================

with tab2:

    st.subheader(
        "Cotação automática no MaisFrete"
    )

    c1, c2 = st.columns(
        2
    )

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
    # DADOS OPERACIONAIS
    # -----------------------------------------------------

    a, b, c = st.columns(
        3
    )

    with a:

        eixos = st.selectbox(
            "Eixos",
            [
                3,
                4,
                5,
                6,
                7,
                9
            ],
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

        margem_empresa = st.number_input(
            "Margem empresa MaisFrete (%)",
            min_value=0.0,
            max_value=100.0,
            value=25.0,
            step=1.0
        )

    # -----------------------------------------------------
    # AJUSTES COMERCIAIS
    # -----------------------------------------------------

    d, e = st.columns(
        2
    )

    with d:

        icms = st.number_input(
            "ICMS adicional (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help="Informe manualmente conforme a operação. Deixe 0 quando não for aplicável."
        )

    with e:

        margem_seguranca = st.number_input(
            "Margem de segurança (%)",
            min_value=0.0,
            max_value=100.0,
            value=0.0,
            step=1.0,
            help="Ajuste comercial para aproximar a estimativa do custo real de mercado."
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
                    "resultado"
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
        "resultado"
    )

    # =====================================================
    # RESULTADOS LOGÍSTICA
    # =====================================================

    if resultado:

        st.success(
            f'{resultado["origem"]} → {resultado["destino"]}'
        )

        x1, x2, x3, x4 = st.columns(
            4
        )

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

        y1, y2, y3 = st.columns(
            3
        )

        y1.metric(
            "Pedágio",
            br_money(
                resultado[
                    "pedagio_total"
                ]
            )
        )

        y2.metric(
            "Frete + pedágio / t",
            br_money(
                resultado[
                    "frete_base_t"
                ]
            )
        )

        y3.metric(
            "Frete final / t",
            br_money(
                resultado[
                    "frete_final_t"
                ]
            )
        )

        # -------------------------------------------------
        # AJUSTES
        # -------------------------------------------------

        z1, z2, z3 = st.columns(
            3
        )

        z1.metric(
            "ICMS aplicado",
            br_money(
                resultado[
                    "icms_t"
                ]
            )
            +
            "/t"
        )

        z2.metric(
            "Margem de segurança",
            br_money(
                resultado[
                    "margem_seguranca_t"
                ]
            )
            +
            "/t"
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
            f"ICMS {resultado['icms_pct']:.1f}% • "
            f"margem de segurança {resultado['margem_seguranca_pct']:.1f}% • "
            "Granel Sólido"
        )

        st.info(
            "Frete final/t = "
            +
            br_money(
                resultado[
                    "frete_emp_t"
                ]
            )
            +
            " frete/t + "
            +
            br_money(
                resultado[
                    "pedagio_t"
                ]
            )
            +
            " pedágio/t + "
            +
            br_money(
                resultado[
                    "icms_t"
                ]
            )
            +
            " ICMS/t + "
            +
            br_money(
                resultado[
                    "margem_seguranca_t"
                ]
            )
            +
            " margem de segurança/t = "
            +
            br_money(
                resultado[
                    "frete_final_t"
                ]
            )
            +
            "/t"
        )


# =========================================================
# V3 — FISCAL
# =========================================================

with tab3:

    st.info(
        "V3 será estruturada após a confirmação do NCM e do tratamento fiscal efetivamente utilizado na NF do FortiPro."
    )
