#!/usr/bin/env python3
from __future__ import annotations

import io
from dataclasses import dataclass

import pandas as pd
import streamlit as st
import exchange_calendars as ec


# ----------------------------
# Exchanges
# ----------------------------

@dataclass(frozen=True)
class ExchangeOption:
    label: str
    code: str


README_EXCHANGE_NAMES: dict[str, str] = {
    "XNYS": "New York Stock Exchange",
    "XCBF": "CBOE Futures",
    "CMES": "Chicago Mercantile Exchange",
    "IEPA": "ICE US",
    "XTSE": "Toronto Stock Exchange",
    "BVMF": "BMF Bovespa",
    "XLON": "London Stock Exchange",
    "XAMS": "Euronext Amsterdam",
    "XBRU": "Euronext Brussels",
    "XLIS": "Euronext Lisbon",
    "XPAR": "Euronext Paris",
    "XFRA": "Frankfurt Stock Exchange",
    "XSWX": "SIX Swiss Exchange",
    "XTKS": "Tokyo Stock Exchange",
    "XASX": "Australian Securities Exchange",
    "XMAD": "Bolsa de Madrid",
    "XMIL": "Borsa Italiana",
    "XNZE": "New Zealand Exchange",
    "XWBO": "Wiener Borse",
    "XHKG": "Hong Kong Stock Exchange",
    "XCSE": "Copenhagen Stock Exchange",
    "XHEL": "Helsinki Stock Exchange",
    "XSTO": "Stockholm Stock Exchange",
    "XOSL": "Oslo Stock Exchange",
    "XDUB": "Irish Stock Exchange",
    "XSES": "Singapore Exchange",
    "XSHG": "Shanghai Stock Exchange",
    "XKRX": "Korea Exchange",
    "XICE": "Iceland Stock Exchange",
    "XWAR": "Poland Stock Exchange",
    "XSGO": "Santiago Stock Exchange",
    "XBOG": "Colombia Securities Exchange",
    "XMEX": "Mexican Stock Exchange",
    "XLIM": "Lima Stock Exchange",
    "XPRA": "Prague Stock Exchange",
    "XBUD": "Budapest Stock Exchange",
    "ASEX": "Athens Stock Exchange",
    "XIST": "Istanbul Stock Exchange",
    "XJSE": "Johannesburg Stock Exchange",
    "XKLS": "Malaysia Stock Exchange",
    "XMOS": "Moscow Exchange",
    "XPHS": "Philippine Stock Exchange",
    "XBKK": "Stock Exchange of Thailand",
    "XIDX": "Indonesia Stock Exchange",
    "XTAI": "Taiwan Stock Exchange Corp.",
    "XBUE": "Buenos Aires Stock Exchange",
    "XKAR": "Pakistan Stock Exchange",
    "XETR": "Xetra",
    "XTAE": "Tel Aviv Stock Exchange",
    "AIXK": "Astana International Exchange",
    "XBSE": "Bucharest Stock Exchange",
    "XSAU": "Saudi Stock Exchange (Tadawul)",
    "XEEE": "European Energy Exchange AG",
    "XHAM": "Hamburg Stock Exchange",
    "XDUS": "Dusseldorf Stock Exchange",
    "XLUX": "Luxembourg Stock Exchange",
    "XTAL": "Tallinn Stock Exchange",
    "XRIS": "Riga Stock Exchange",
    "XLIT": "Vilnius Stock Exchange",
    "XCYS": "Cyprus Stock Exchange",
    "XBDA": "Bermuda Stock Exchange",
    "XZAG": "Zagreb Stock Exchange",
    "XLJU": "Ljubljana Stock Exchange",
    "XBRA": "Bratislava Stock Exchange",
    "XBEL": "Belgrade Stock Exchange",
}


@st.cache_data
def build_exchanges_from_readme(include_aliases: bool = False) -> list[ExchangeOption]:
    """Build exchange options using only calendar codes available in the installed package."""
    available = set(ec.get_calendar_names(include_aliases=include_aliases))

    options: list[ExchangeOption] = []
    for code, name in README_EXCHANGE_NAMES.items():
        if code in available:
            options.append(ExchangeOption(label=f"{name} [{code}]", code=code))

    options.sort(key=lambda item: (item.label.lower(), item.code))
    return options


EXCHANGES = build_exchanges_from_readme(include_aliases=False)


# ----------------------------
# Holidays extraction
# ----------------------------

def _regular_holidays_df(
    cal,
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp
) -> pd.DataFrame:
    regular_holidays = cal.regular_holidays.holidays(start=start, end=end, return_name=True)

    if isinstance(regular_holidays, pd.Series):
        df = (
            regular_holidays.rename("holiday")
            .to_frame()
            .reset_index()
            .rename(columns={"index": "date"})
        )
    else:
        df = pd.DataFrame({
            "date": pd.to_datetime(regular_holidays),
            "holiday": "Holiday",
        })

    df["exchange"] = exchange_code
    df["date"] = pd.to_datetime(df["date"])
    return df[["date", "exchange", "holiday"]]


def _adhoc_holidays_df(
    cal,
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp
) -> pd.DataFrame:
    adhoc_list = list(getattr(cal, "adhoc_holidays", []))
    if not adhoc_list:
        return pd.DataFrame(columns=["date", "exchange", "holiday"])

    adhoc_dates = pd.to_datetime(adhoc_list)
    adhoc_dates = adhoc_dates[(adhoc_dates >= start) & (adhoc_dates <= end)]
    if len(adhoc_dates) == 0:
        return pd.DataFrame(columns=["date", "exchange", "holiday"])

    df = pd.DataFrame({
        "date": pd.to_datetime(adhoc_dates),
        "exchange": exchange_code,
        "holiday": "Ad-hoc / special closing",
    })
    return df[["date", "exchange", "holiday"]]


def _closures_for_exchange(
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp
) -> pd.DataFrame:
    """Return all closures (regular + ad-hoc) for one exchange in [start, end]."""
    cal = ec.get_calendar(exchange_code)

    regular_df = _regular_holidays_df(cal, exchange_code, start, end)
    adhoc_df = _adhoc_holidays_df(cal, exchange_code, start, end)

    if adhoc_df.empty:
        result = regular_df.copy()
    else:
        result = pd.concat([regular_df, adhoc_df], ignore_index=True)

    result = (
        result.drop_duplicates(subset=["date", "exchange", "holiday"])
        .sort_values(["date", "exchange", "holiday"], ascending=[True, True, True])
        .reset_index(drop=True)
    )
    return result


@st.cache_data(show_spinner=False)
def build_table(
    exchanges: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    view_mode: str,
) -> pd.DataFrame:
    """
    Build the raw dataframe.

    Long view:
        columns -> date, exchange, holiday

    Wide view:
        columns -> date, one column per exchange
    """
    if not exchanges:
        return pd.DataFrame()

    frames = [_closures_for_exchange(code, start, end) for code in exchanges]
    result = pd.concat(frames, ignore_index=True)

    result = (
        result.sort_values(["date", "exchange", "holiday"], ascending=[True, True, True])
        .reset_index(drop=True)
    )

    if view_mode == "Wide":
        wide = (
            result.pivot_table(
                index="date",
                columns="exchange",
                values="holiday",
                aggfunc=lambda s: " | ".join(sorted(set(map(str, s))))
            )
            .sort_index(ascending=True)
        )
        wide = wide.reindex(columns=exchanges)
        wide = wide.reset_index()
        wide.columns.name = None
        return wide

    return result[["date", "exchange", "holiday"]]


def prepare_df_for_view(df: pd.DataFrame) -> pd.DataFrame:
    """Return a dataframe prepared for Streamlit display."""
    if df.empty:
        return df.copy()

    out = df.copy()

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"]).dt.date.astype(str)

    return out


def prepare_df_for_output(df: pd.DataFrame) -> pd.DataFrame:
    """Return a copy suitable for CSV and Excel output."""
    out = df.copy()

    if "_date_sort" in out.columns:
        out = out.drop(columns=["_date_sort"])

    if "date" in out.columns:
        out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.date.astype(str)

    return out.fillna("")


def dataframe_to_csv_bytes(df: pd.DataFrame) -> bytes:
    export_df = prepare_df_for_output(df)
    return export_df.to_csv(index=False, encoding="utf-8").encode("utf-8")


def dataframe_to_excel_bytes(df: pd.DataFrame) -> bytes:
    export_df = prepare_df_for_output(df)
    buffer = io.BytesIO()

    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        export_df.to_excel(writer, index=False, sheet_name="Holidays")

    buffer.seek(0)
    return buffer.getvalue()


# ----------------------------
# Streamlit app
# ----------------------------

def main():
    st.set_page_config(
        page_title="Exchange Holidays",
        layout="wide",
    )

    st.title("Exchange Holidays")
    st.caption("Market holiday calendar by exchange")

    exchange_label_to_code = {option.label: option.code for option in EXCHANGES}
    exchange_labels = list(exchange_label_to_code.keys())

    default_labels = [
        label for label, code in exchange_label_to_code.items()
        if code == "XNYS"
    ]

    with st.sidebar:
        st.header("Options")

        selected_labels = st.multiselect(
            "Exchanges",
            options=exchange_labels,
            default=default_labels,
        )

        start_date = st.date_input(
            "From",
            value=pd.Timestamp(2026, 1, 1).date(),
        )

        end_date = st.date_input(
            "To",
            value=pd.Timestamp(2026, 12, 31).date(),
        )

        view_label = st.selectbox(
            "View",
            options=["Long (rows)", "Wide (columns by exchange)"],
            index=0,
        )

        generate = st.button("Generate table", type="primary", use_container_width=True)

    if "generated" not in st.session_state:
        st.session_state.generated = False
    if "raw_df" not in st.session_state:
        st.session_state.raw_df = pd.DataFrame()
    if "view_df" not in st.session_state:
        st.session_state.view_df = pd.DataFrame()
    if "selected_codes" not in st.session_state:
        st.session_state.selected_codes = []

    if generate:
        if not selected_labels:
            st.error("Select at least one exchange.")
        elif end_date < start_date:
            st.error("'To' must be greater than or equal to 'From'.")
        else:
            selected_codes = sorted(
                {exchange_label_to_code[label] for label in selected_labels}
            )
            start = pd.Timestamp(start_date)
            end = pd.Timestamp(end_date)
            view_mode = "Wide" if view_label.startswith("Wide") else "Long"

            try:
                raw_df = build_table(
                    exchanges=selected_codes,
                    start=start,
                    end=end,
                    view_mode=view_mode,
                )
                view_df = prepare_df_for_view(raw_df)
            except ModuleNotFoundError as exc:
                st.error(f"Missing dependency: {exc}")
                return
            except Exception as exc:
                st.error(f"Error while calculating exchange closures: {exc}")
                return

            st.session_state.generated = True
            st.session_state.raw_df = raw_df
            st.session_state.view_df = view_df
            st.session_state.selected_codes = selected_codes
            st.session_state.view_mode = view_mode

    if st.session_state.generated:
        raw_df = st.session_state.raw_df
        view_df = st.session_state.view_df
        selected_codes = st.session_state.selected_codes
        view_mode = st.session_state.view_mode

        st.info(
            f"Exchanges: {', '.join(selected_codes)} | "
            f"Rows: {len(view_df)} | View: {view_mode}"
        )

        if view_df.empty:
            st.warning("No closures found for the selected criteria.")
        else:
            st.dataframe(view_df, use_container_width=True, hide_index=True)

            col1, col2 = st.columns(2)

            with col1:
                st.download_button(
                    label="Download CSV",
                    data=dataframe_to_csv_bytes(raw_df),
                    file_name="holidays.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with col2:
                try:
                    excel_bytes = dataframe_to_excel_bytes(raw_df)
                    st.download_button(
                        label="Download Excel",
                        data=excel_bytes,
                        file_name="holidays.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                except ModuleNotFoundError:
                    st.warning("The 'openpyxl' package is missing. Install it with: pip install openpyxl")
    else:
        st.write("Choose exchanges, date range, and view mode from the sidebar, then click **Generate table**.")


if __name__ == "__main__":
    main()
