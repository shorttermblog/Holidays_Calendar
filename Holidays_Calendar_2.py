#!/usr/bin/env python3
from __future__ import annotations

import io
from dataclasses import dataclass

import exchange_calendars as ec
import pandas as pd
import requests
import streamlit as st


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

    # Additional Asian exchanges
    "XBOM": "BSE (Bombay Stock Exchange)",
    "XSES": "Singapore Exchange",
    "XSHG": "Shanghai Stock Exchange",
    "XNSE": "National Stock Exchange of India",
}


# XNSE is not handled natively by exchange_calendars.
CUSTOM_EXCHANGE_CODES = {"XNSE"}


@st.cache_data
def build_exchanges_from_readme(
    include_aliases: bool = False,
) -> list[ExchangeOption]:
    """
    Build the exchange list shown in the UI.

    Native exchanges must exist in exchange_calendars.
    Custom exchanges are explicitly included.
    """

    available = set(
        ec.get_calendar_names(
            include_aliases=include_aliases
        )
    )

    options: list[ExchangeOption] = []

    for code, name in README_EXCHANGE_NAMES.items():
        if code in available or code in CUSTOM_EXCHANGE_CODES:
            options.append(
                ExchangeOption(
                    label=f"{name} [{code}]",
                    code=code,
                )
            )

    options.sort(
        key=lambda item: (
            item.label.lower(),
            item.code,
        )
    )

    return options


EXCHANGES = build_exchanges_from_readme(
    include_aliases=False
)


# ----------------------------
# Common helpers
# ----------------------------

def _empty_holiday_df() -> pd.DataFrame:
    """
    Return an empty holiday dataframe with consistent columns.
    """

    return pd.DataFrame(
        columns=[
            "date",
            "exchange",
            "holiday",
        ]
    )


# ----------------------------
# exchange_calendars extraction
# ----------------------------

def _regular_holidays_df(
    cal,
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Return regular holidays for an exchange.

    Some precomputed calendars, including XBOM, XSES
    and XSHG, can have regular_holidays = None.
    """

    regular_calendar = getattr(
        cal,
        "regular_holidays",
        None,
    )

    if regular_calendar is None:
        return _empty_holiday_df()

    regular_holidays = regular_calendar.holidays(
        start=start,
        end=end,
        return_name=True,
    )

    if isinstance(regular_holidays, pd.Series):
        df = (
            regular_holidays
            .rename("holiday")
            .to_frame()
            .reset_index()
            .rename(columns={"index": "date"})
        )

    else:
        df = pd.DataFrame(
            {
                "date": pd.to_datetime(
                    regular_holidays
                ),
                "holiday": "Holiday",
            }
        )

    if df.empty:
        return _empty_holiday_df()

    df["exchange"] = exchange_code
    df["date"] = pd.to_datetime(df["date"])

    return df[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]


def _adhoc_holidays_df(
    cal,
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Return ad-hoc or precomputed holidays.

    Precomputed calendars such as XBOM, XSES and XSHG
    can expose their holiday dates through adhoc_holidays.

    Important:
    adhoc_holidays may be a pandas DatetimeIndex.
    It must NOT be evaluated directly as a boolean.
    """

    adhoc_holidays = getattr(
        cal,
        "adhoc_holidays",
        None,
    )

    if adhoc_holidays is None:
        return _empty_holiday_df()

    adhoc_list = list(adhoc_holidays)

    if len(adhoc_list) == 0:
        return _empty_holiday_df()

    adhoc_dates = pd.to_datetime(
        adhoc_list
    )

    start = pd.Timestamp(start)
    end = pd.Timestamp(end)

    adhoc_dates = adhoc_dates[
        (adhoc_dates >= start)
        & (adhoc_dates <= end)
    ]

    if len(adhoc_dates) == 0:
        return _empty_holiday_df()

    df = pd.DataFrame(
        {
            "date": pd.to_datetime(
                adhoc_dates
            ),
            "exchange": exchange_code,
            "holiday": "Holiday / special closing",
        }
    )

    return df[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]


# ----------------------------
# NSE India custom calendar
# ----------------------------

NSE_HOME_URL = "https://www.nseindia.com"

NSE_HOLIDAY_URL = (
    "https://www.nseindia.com/api/holiday-master"
)


def _nse_headers() -> dict[str, str]:
    """
    Browser-like headers for NSE requests.
    """

    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/154.0.0.0 "
            "Safari/537.36"
        ),
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": (
            "https://www.nseindia.com/"
            "resources/exchange-communication-holidays"
        ),
        "Connection": "keep-alive",
    }


@st.cache_data(
    ttl=21600,
    show_spinner=False,
)
def _fetch_nse_holidays_for_year(
    year: int,
) -> pd.DataFrame:
    """
    Fetch official NSE Capital Market trading holidays.

    CM = Capital Market / cash equities.
    """

    headers = _nse_headers()

    with requests.Session() as session:

        # Attempt to initialise NSE cookies.
        #
        # IMPORTANT:
        # NSE may return 403 for the homepage even though
        # the API endpoint itself remains accessible.
        # Therefore DO NOT call raise_for_status() here.
        try:
            session.get(
                NSE_HOME_URL,
                headers=headers,
                timeout=20,
            )
        except requests.RequestException:
            pass

        # Actual holiday API request
        response = session.get(
            NSE_HOLIDAY_URL,
            params={
                "type": "trading",
                "year": str(year),
            },
            headers=headers,
            timeout=30,
        )

        # If NSE rejects the API call, try once again
        # after refreshing the session/cookies.
        if response.status_code in {401, 403}:

            session.cookies.clear()

            try:
                session.get(
                    NSE_HOME_URL,
                    headers=headers,
                    timeout=20,
                )
            except requests.RequestException:
                pass

            response = session.get(
                NSE_HOLIDAY_URL,
                params={
                    "type": "trading",
                    "year": str(year),
                },
                headers=headers,
                timeout=30,
            )

        # ONLY the actual API response is required to succeed.
        response.raise_for_status()

        payload = response.json()

    rows = payload.get("CM")

    if not isinstance(rows, list):
        raise RuntimeError(
            "NSE holiday response does not contain "
            "the expected 'CM' Capital Market segment."
        )

    records: list[dict[str, object]] = []

    for row in rows:

        raw_date = row.get("tradingDate")

        if not raw_date:
            continue

        date = pd.to_datetime(
            raw_date,
            format="%d-%b-%Y",
            errors="coerce",
        )

        if pd.isna(date):
            continue

        # Exclude ordinary Saturday/Sunday closures.
        if date.weekday() >= 5:
            continue

        # Ignore data outside requested year.
        if date.year != year:
            continue

        holiday = (
            row.get("description")
            or row.get("holidayDescription")
            or "NSE trading holiday"
        )

        records.append(
            {
                "date": date.normalize(),
                "exchange": "XNSE",
                "holiday": str(holiday).strip(),
            }
        )

    if not records:
        raise RuntimeError(
            f"NSE returned no weekday Capital Market "
            f"holidays for {year}. "
            f"The calendar for that year may not yet "
            f"have been published."
        )

    result = pd.DataFrame(records)

    result = (
        result
        .drop_duplicates(
            subset=[
                "date",
                "exchange",
                "holiday",
            ]
        )
        .sort_values(
            [
                "date",
                "exchange",
                "holiday",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    return result[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]

def _closures_for_nse(
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Return NSE cash-equity closures in the requested range.
    """

    start = pd.Timestamp(start).normalize()
    end = pd.Timestamp(end).normalize()

    if end < start:
        return _empty_holiday_df()

    frames: list[pd.DataFrame] = []

    for year in range(
        start.year,
        end.year + 1,
    ):

        year_df = _fetch_nse_holidays_for_year(
            year
        )

        if not year_df.empty:
            frames.append(year_df)

    if not frames:
        return _empty_holiday_df()

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result["date"] = pd.to_datetime(
        result["date"]
    )

    result = result[
        (result["date"] >= start)
        & (result["date"] <= end)
    ]

    result = (
        result
        .drop_duplicates(
            subset=[
                "date",
                "exchange",
                "holiday",
            ]
        )
        .sort_values(
            [
                "date",
                "exchange",
                "holiday",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    return result[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]


# ----------------------------
# Exchange dispatcher
# ----------------------------

def _closures_for_exchange(
    exchange_code: str,
    start: pd.Timestamp,
    end: pd.Timestamp,
) -> pd.DataFrame:
    """
    Return holiday closures for one exchange.

    XNSE:
        custom NSE implementation.

    Everything else:
        exchange_calendars.
    """

    if exchange_code == "XNSE":
        return _closures_for_nse(
            start=start,
            end=end,
        )

    cal = ec.get_calendar(
        exchange_code
    )

    regular_df = _regular_holidays_df(
        cal=cal,
        exchange_code=exchange_code,
        start=start,
        end=end,
    )

    adhoc_df = _adhoc_holidays_df(
        cal=cal,
        exchange_code=exchange_code,
        start=start,
        end=end,
    )

    frames: list[pd.DataFrame] = []

    if not regular_df.empty:
        frames.append(regular_df)

    if not adhoc_df.empty:
        frames.append(adhoc_df)

    if not frames:
        return _empty_holiday_df()

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result = (
        result
        .drop_duplicates(
            subset=[
                "date",
                "exchange",
                "holiday",
            ]
        )
        .sort_values(
            [
                "date",
                "exchange",
                "holiday",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    return result[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]


# ----------------------------
# Table generation
# ----------------------------

@st.cache_data(
    show_spinner=False
)
def build_table(
    exchanges: list[str],
    start: pd.Timestamp,
    end: pd.Timestamp,
    view_mode: str,
) -> pd.DataFrame:
    """
    Build the holiday dataframe.

    Long:
        date, exchange, holiday

    Wide:
        date + one column per exchange
    """

    if not exchanges:
        return pd.DataFrame()

    frames: list[pd.DataFrame] = []

    for code in exchanges:

        exchange_df = _closures_for_exchange(
            exchange_code=code,
            start=start,
            end=end,
        )

        if not exchange_df.empty:
            frames.append(exchange_df)

    if not frames:

        if view_mode == "Wide":
            return pd.DataFrame(
                columns=[
                    "date",
                    *exchanges,
                ]
            )

        return _empty_holiday_df()

    result = pd.concat(
        frames,
        ignore_index=True,
    )

    result = (
        result
        .sort_values(
            [
                "date",
                "exchange",
                "holiday",
            ],
            ascending=[
                True,
                True,
                True,
            ],
        )
        .reset_index(drop=True)
    )

    if view_mode == "Wide":

        wide = (
            result
            .pivot_table(
                index="date",
                columns="exchange",
                values="holiday",
                aggfunc=lambda s: " | ".join(
                    sorted(
                        set(
                            map(str, s)
                        )
                    )
                ),
            )
            .sort_index(
                ascending=True
            )
        )

        wide = wide.reindex(
            columns=exchanges
        )

        wide = wide.reset_index()
        wide.columns.name = None

        return wide

    return result[
        [
            "date",
            "exchange",
            "holiday",
        ]
    ]


# ----------------------------
# Display / export
# ----------------------------

def prepare_df_for_view(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare dataframe for Streamlit display.
    """

    if df.empty:
        return df.copy()

    out = df.copy()

    if "date" in out.columns:

        out["date"] = (
            pd.to_datetime(
                out["date"]
            )
            .dt.date
            .astype(str)
        )

    return out


def prepare_df_for_output(
    df: pd.DataFrame,
) -> pd.DataFrame:
    """
    Prepare dataframe for CSV / Excel export.
    """

    out = df.copy()

    if "_date_sort" in out.columns:
        out = out.drop(
            columns=["_date_sort"]
        )

    if "date" in out.columns:

        out["date"] = (
            pd.to_datetime(
                out["date"],
                errors="coerce",
            )
            .dt.date
            .astype(str)
        )

    return out.fillna("")


def dataframe_to_csv_bytes(
    df: pd.DataFrame,
) -> bytes:
    """
    Convert dataframe to CSV bytes.
    """

    export_df = prepare_df_for_output(
        df
    )

    return export_df.to_csv(
        index=False,
        encoding="utf-8",
    ).encode("utf-8")


def dataframe_to_excel_bytes(
    df: pd.DataFrame,
) -> bytes:
    """
    Convert dataframe to XLSX bytes.
    """

    export_df = prepare_df_for_output(
        df
    )

    buffer = io.BytesIO()

    with pd.ExcelWriter(
        buffer,
        engine="openpyxl",
    ) as writer:

        export_df.to_excel(
            writer,
            index=False,
            sheet_name="Holidays",
        )

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

    st.title(
        "Exchange Holidays"
    )

    st.caption(
        "Market holiday calendar by exchange"
    )

    exchange_label_to_code = {
        option.label: option.code
        for option in EXCHANGES
    }

    exchange_labels = list(
        exchange_label_to_code.keys()
    )

    default_labels = [
        label
        for label, code
        in exchange_label_to_code.items()
        if code == "XNYS"
    ]

    with st.sidebar:

        st.header(
            "Options"
        )

        selected_labels = st.multiselect(
            "Exchanges",
            options=exchange_labels,
            default=default_labels,
        )

        start_date = st.date_input(
            "From",
            value=pd.Timestamp(
                2026,
                1,
                1,
            ).date(),
        )

        end_date = st.date_input(
            "To",
            value=pd.Timestamp(
                2026,
                12,
                31,
            ).date(),
        )

        view_label = st.selectbox(
            "View",
            options=[
                "Long (rows)",
                "Wide (columns by exchange)",
            ],
            index=0,
        )

        generate = st.button(
            "Generate table",
            type="primary",
            use_container_width=True,
        )

    # ----------------------------
    # Session state
    # ----------------------------

    if "generated" not in st.session_state:
        st.session_state.generated = False

    if "raw_df" not in st.session_state:
        st.session_state.raw_df = pd.DataFrame()

    if "view_df" not in st.session_state:
        st.session_state.view_df = pd.DataFrame()

    if "selected_codes" not in st.session_state:
        st.session_state.selected_codes = []

    if "view_mode" not in st.session_state:
        st.session_state.view_mode = "Long"

    # ----------------------------
    # Generate table
    # ----------------------------

    if generate:

        if not selected_labels:

            st.error(
                "Select at least one exchange."
            )

        elif end_date < start_date:

            st.error(
                "'To' must be greater than "
                "or equal to 'From'."
            )

        else:

            selected_codes = sorted(
                {
                    exchange_label_to_code[label]
                    for label in selected_labels
                }
            )

            start = pd.Timestamp(
                start_date
            )

            end = pd.Timestamp(
                end_date
            )

            view_mode = (
                "Wide"
                if view_label.startswith("Wide")
                else "Long"
            )

            try:

                raw_df = build_table(
                    exchanges=selected_codes,
                    start=start,
                    end=end,
                    view_mode=view_mode,
                )

                view_df = prepare_df_for_view(
                    raw_df
                )

            except ModuleNotFoundError as exc:

                st.error(
                    f"Missing dependency: {exc}"
                )
                return

            except requests.RequestException as exc:

                st.error(
                    "Unable to retrieve NSE holiday data: "
                    f"{exc}"
                )
                return

            except Exception as exc:

                st.error(
                    "Error while calculating "
                    f"exchange closures: {exc}"
                )
                return

            st.session_state.generated = True
            st.session_state.raw_df = raw_df
            st.session_state.view_df = view_df
            st.session_state.selected_codes = selected_codes
            st.session_state.view_mode = view_mode

    # ----------------------------
    # Results
    # ----------------------------

    if st.session_state.generated:

        raw_df = st.session_state.raw_df
        view_df = st.session_state.view_df
        selected_codes = st.session_state.selected_codes
        view_mode = st.session_state.view_mode

        st.info(
            f"Exchanges: {', '.join(selected_codes)} | "
            f"Rows: {len(view_df)} | "
            f"View: {view_mode}"
        )

        if view_df.empty:

            st.warning(
                "No closures found for "
                "the selected criteria."
            )

        else:

            st.dataframe(
                view_df,
                use_container_width=True,
                hide_index=True,
            )

            col1, col2 = st.columns(2)

            with col1:

                st.download_button(
                    label="Download CSV",
                    data=dataframe_to_csv_bytes(
                        raw_df
                    ),
                    file_name="holidays.csv",
                    mime="text/csv",
                    use_container_width=True,
                )

            with col2:

                try:

                    excel_bytes = dataframe_to_excel_bytes(
                        raw_df
                    )

                    st.download_button(
                        label="Download Excel",
                        data=excel_bytes,
                        file_name="holidays.xlsx",
                        mime=(
                            "application/"
                            "vnd.openxmlformats-officedocument."
                            "spreadsheetml.sheet"
                        ),
                        use_container_width=True,
                    )

                except ModuleNotFoundError:

                    st.warning(
                        "The 'openpyxl' package is missing. "
                        "Install it with: "
                        "pip install openpyxl"
                    )

    else:

        st.write(
            "Choose exchanges, date range, and view mode "
            "from the sidebar, then click "
            "**Generate table**."
        )


if __name__ == "__main__":
    main()
