import math

# --- CONFIGURATION (from PineScript inputs) ---
WEIGHT_STEP = 0.87
WEIGHT_VOL = 0.87
PERIOD_STEP = 100
PERIOD_VOL = 100

MNOZNIK_QTY = 10.0
MINIMALNY_ZYSK_PROC_CELU = 0.2
LTC_NA_KONTRAKT = 0.01

WLACZ_MOD_WIELKOSC = True
PROG_KONTRAKTOW_MOD = 10
SILA_SPADKU_MOD_WIELKOSC = 0.5

WLACZ_MOD_CZAS_OGOLNY = True
SILA_SPADKU_CZAS_OGOLNY = 0.1

WLACZ_MOD_CZAS_W_ZYSKU = True
CZAS_AKTYWACJI_W_ZYSKU = 30
SILA_SPADKU_CZAS_W_ZYSKU = 0.2

# ---------------------------------------------

def calculate_step(candles, index, period=100, weight=0.87):
    start_idx = max(0, index - period + 1)
    slice_candles = candles[start_idx:index+1]
    slice_candles.reverse() 
    
    suma_kroku = 0.0
    suma_wag_kroku = 0.0
    
    for i in range(len(slice_candles)):
        c = slice_candles[i]
        waga_kroku = math.pow(weight, i)
        high = c['high'] if isinstance(c, dict) else c.high
        low = c['low'] if isinstance(c, dict) else c.low
        suma_kroku += (high - low) * waga_kroku
        suma_wag_kroku += waga_kroku
        
    if suma_wag_kroku == 0: return 0
    return (suma_kroku / suma_wag_kroku) * 2

def f_oblicz_sredni_wolumen(candles, index, period=100, weight=0.87):
    # Only compute this if we need it for the panel at the very end
    # Simplified approach: return average volume of the last 100 bars
    # In full PineScript it's a double moving average. Let's do a simple SMA for speed, 
    # as the user said it's just for the informational panel.
    start_idx = max(0, index - period + 1)
    slice_candles = candles[start_idx:index+1]
    if not slice_candles: return 0.0
    vol_sum = 0.0
    for c in slice_candles:
        vol = c['volume'] if isinstance(c, dict) and 'volume' in c else getattr(c, 'volume', 0)
        vol_sum += vol
    return vol_sum / len(slice_candles)

def apply_strategy_ms(candles, interval_ms=60000, mnoznik_qty_long=10.0, mnoznik_qty_short=10.0,
                      hist_long_avg_min=0.0, hist_long_count=0, hist_short_avg_min=0.0, hist_short_count=0,
                      hist_long_total_averagings=0, hist_short_total_averagings=0, initial_state=None, process_from_index=0, treat_last_as_live=True):
    """
    Simulates the whole MS v2.0.5 strategy.
    Returns:
      results: list of indicator lines {time, value}
      markers: list of lightweight-chart markers {time, position, color, shape, text}
      panel:   dict with current state info
    """
    if not candles:
        return [], [], {}

    m_sw = interval_ms / 60000.0 if interval_ms else 1.0

    results = []
    markers = []
    closed_trades = []

    if initial_state:
        linia = initial_state.get('linia')
        trend = initial_state.get('trend', 0)
        trend_history = initial_state.get('trend_history', [])
        linia_history = initial_state.get('linia_history', [])
        
        L_system_aktywny = initial_state.get('L_system_aktywny', False)
        L_poziomy_linii = initial_state.get('L_poziomy_linii', [])
        L_wartosci_linii = initial_state.get('L_wartosci_linii', [])
        L_najnizszy_dolek = initial_state.get('L_najnizszy_dolek')
        L_licznik_nowych_dolkow = initial_state.get('L_licznik_nowych_dolkow', 0)
        L_timestamp_otwarcia = initial_state.get('L_timestamp_otwarcia', 0)
        
        L_poziom_niebieskiej_linii = initial_state.get('L_poziom_niebieskiej_linii')
        L_poziom_celu_minimalnego = initial_state.get('L_poziom_celu_minimalnego')
        L_poziom_celu_bazowego = initial_state.get('L_poziom_celu_bazowego')
        L_poziom_celu_ostatecznego = initial_state.get('L_poziom_celu_ostatecznego')
        L_biezacy_pnl = initial_state.get('L_biezacy_pnl', 0.0)
        L_najnizszy_pnl_w_pozycji = initial_state.get('L_najnizszy_pnl_w_pozycji', 0.0)
        
        L_suma_wszystkich_dolkow = initial_state.get('L_suma_wszystkich_dolkow', hist_long_total_averagings)
        L_licznik_zamknietych_pozycji = initial_state.get('L_licznik_zamknietych_pozycji', hist_long_count)
        L_suma_minut_w_pozycjach = initial_state.get('L_suma_minut_w_pozycjach', hist_long_avg_min * hist_long_count)
        L_max_ilosc_usrednien = initial_state.get('L_max_ilosc_usrednien', 0)
        
        S_system_aktywny = initial_state.get('S_system_aktywny', False)
        S_poziomy_linii = initial_state.get('S_poziomy_linii', [])
        S_wartosci_linii = initial_state.get('S_wartosci_linii', [])
        S_najwyzszy_szczyt = initial_state.get('S_najwyzszy_szczyt')
        S_licznik_nowych_szczytow = initial_state.get('S_licznik_nowych_szczytow', 0)
        S_timestamp_otwarcia = initial_state.get('S_timestamp_otwarcia', 0)
        
        S_poziom_niebieskiej_linii = initial_state.get('S_poziom_niebieskiej_linii')
        S_poziom_celu_minimalnego = initial_state.get('S_poziom_celu_minimalnego')
        S_poziom_celu_bazowego = initial_state.get('S_poziom_celu_bazowego')
        S_poziom_celu_ostatecznego = initial_state.get('S_poziom_celu_ostatecznego')
        S_biezacy_pnl = initial_state.get('S_biezacy_pnl', 0.0)
        S_najnizszy_pnl_w_pozycji = initial_state.get('S_najnizszy_pnl_w_pozycji', 0.0)
        
        S_suma_wszystkich_szczytow = initial_state.get('S_suma_wszystkich_szczytow', hist_short_total_averagings)
        S_licznik_zamknietych_pozycji = initial_state.get('S_licznik_zamknietych_pozycji', hist_short_count)
        S_suma_minut_w_pozycjach = initial_state.get('S_suma_minut_w_pozycjach', hist_short_avg_min * hist_short_count)
        S_max_ilosc_usrednien = initial_state.get('S_max_ilosc_usrednien', 0)
    else:
        linia = None
        trend = 0
        trend_history = []
        linia_history = []
        
        L_system_aktywny = False
        L_poziomy_linii = []
        L_wartosci_linii = []
        L_najnizszy_dolek = None
        L_licznik_nowych_dolkow = 0
        L_timestamp_otwarcia = 0
        
        L_poziom_niebieskiej_linii = None
        L_poziom_celu_minimalnego = None
        L_poziom_celu_bazowego = None
        L_poziom_celu_ostatecznego = None
        L_biezacy_pnl = 0.0
        L_najnizszy_pnl_w_pozycji = 0.0
        
        L_suma_wszystkich_dolkow = hist_long_total_averagings
        L_licznik_zamknietych_pozycji = hist_long_count
        L_suma_minut_w_pozycjach = hist_long_avg_min * hist_long_count
        L_max_ilosc_usrednien = 0
        
        S_system_aktywny = False
        S_poziomy_linii = []
        S_wartosci_linii = []
        S_najwyzszy_szczyt = None
        S_licznik_nowych_szczytow = 0
        S_timestamp_otwarcia = 0
        
        S_poziom_niebieskiej_linii = None
        S_poziom_celu_minimalnego = None
        S_poziom_celu_bazowego = None
        S_poziom_celu_ostatecznego = None
        S_biezacy_pnl = 0.0
        S_najnizszy_pnl_w_pozycji = 0.0
        
        S_suma_wszystkich_szczytow = hist_short_total_averagings
        S_licznik_zamknietych_pozycji = hist_short_count
        S_suma_minut_w_pozycjach = hist_short_avg_min * hist_short_count
        S_max_ilosc_usrednien = 0

    for i in range(process_from_index, len(candles)):
        c = candles[i]
        timestamp = c['timestamp'] if isinstance(c, dict) else c.timestamp
        ts_sec = int(timestamp // 1000)
        open_price = c['open'] if isinstance(c, dict) else c.open
        high_price = c['high'] if isinstance(c, dict) else c.high
        low_price = c['low'] if isinstance(c, dict) else c.low
        close_price = c['close'] if isinstance(c, dict) else c.close
        
        krok = calculate_step(candles, i, period=PERIOD_STEP, weight=WEIGHT_STEP)
        
        zmiana_w_gore_na_tej_swiecy = False
        zmiana_w_dol_na_tej_swiecy = False
        
        if linia is None:
            linia = close_price
        else:
            if trend == 1:
                if low_price <= linia - 2 * krok and not zmiana_w_gore_na_tej_swiecy:
                    linia -= 2 * krok
                    trend = -1
                    zmiana_w_dol_na_tej_swiecy = True
                elif high_price >= linia + krok:
                    linia += krok
            elif trend == -1:
                if high_price >= linia + 2 * krok and not zmiana_w_dol_na_tej_swiecy:
                    linia += 2 * krok
                    trend = 1
                    zmiana_w_gore_na_tej_swiecy = True
                elif low_price <= linia - krok:
                    linia -= krok
            else:
                if high_price > linia:
                    trend = 1
                    linia += krok
                elif low_price < linia:
                    trend = -1
                    linia -= krok
                    
        linia_history.append(linia)
        trend_history.append(trend)
        prev_trend = trend_history[-2] if len(trend_history) > 1 else trend
        
        pierwszy_zielony = (trend == 1 and prev_trend == -1)
        pierwszy_czerwony = (trend == -1 and prev_trend == 1)
        
        # ---------------------------------------------------------
        # LONG STRATEGY
        # ---------------------------------------------------------
        is_live_candle = False
        if treat_last_as_live:
            is_live_candle = (i == len(candles) - 1)
        
        if pierwszy_zielony and not is_live_candle:
            if not L_system_aktywny:
                L_system_aktywny = True
                L_timestamp_otwarcia = timestamp
                L_najnizszy_dolek = linia
                L_licznik_nowych_dolkow = 0
                L_poziomy_linii.append(linia)
                L_wartosci_linii.append(1.0)
                
                markers.append({
                    "time": ts_sec,
                    "position": "belowBar",
                    "color": "#235325",
                    "shape": "arrowUp",
                    "text": "L_Otwarcie\n(waga: 1)"
                })
            else:
                dol_nowego_bloczku = linia - krok
                najnizsza_istniejaca = min(L_poziomy_linii) if L_poziomy_linii else linia
                if dol_nowego_bloczku < najnizsza_istniejaca and not is_live_candle:
                    L_poziomy_linii.append(linia)
                    qty_trend = max(1.0, float(L_licznik_nowych_dolkow))
                    L_wartosci_linii.append(qty_trend)
                    
                    markers.append({
                        "time": ts_sec,
                        "position": "belowBar",
                        "color": "#1c441d",
                        "shape": "arrowUp",
                        "text": f"L_Uśrednienie\n(waga: {int(qty_trend)})"
                    })

        if L_system_aktywny:
            if trend == -1:
                if L_najnizszy_dolek is None or (linia + krok) < L_najnizszy_dolek:
                    L_najnizszy_dolek = linia
                    L_licznik_nowych_dolkow += 1
            
            if len(L_wartosci_linii) > 0:
                koszt_long = sum([L_poziomy_linii[j] * (L_wartosci_linii[j] * mnoznik_qty_long * LTC_NA_KONTRAKT) for j in range(len(L_poziomy_linii))])
                total_ltc = sum(L_wartosci_linii) * mnoznik_qty_long * LTC_NA_KONTRAKT
                
                # Use low_price instead of close_price to calculate the worst-case PNL during the candle
                wartosc_rynkowa = total_ltc * low_price 
                L_biezacy_pnl_worst_case = wartosc_rynkowa - koszt_long
                L_najnizszy_pnl_w_pozycji = min(L_najnizszy_pnl_w_pozycji, L_biezacy_pnl_worst_case)
                L_biezacy_pnl = (total_ltc * close_price) - koszt_long # Store actual for panel

        if L_system_aktywny and len(L_poziomy_linii) > 0:
            suma_iloczynow = sum([L_poziomy_linii[j] * L_wartosci_linii[j] for j in range(len(L_poziomy_linii))])
            suma_wag = sum(L_wartosci_linii)
            L_poziom_niebieskiej_linii = suma_iloczynow / suma_wag
            L_poziom_celu_minimalnego = L_poziom_niebieskiej_linii * (1 + MINIMALNY_ZYSK_PROC_CELU / 100.0)
            
            total_ltc = sum(L_wartosci_linii) * mnoznik_qty_long * LTC_NA_KONTRAKT
            strata_na_jednostke = abs(L_najnizszy_pnl_w_pozycji) / total_ltc if total_ltc > 0 else 0
            cel_z_pnl = L_poziom_niebieskiej_linii + (strata_na_jednostke * 2)
            L_poziom_celu_bazowego = max(cel_z_pnl, L_poziom_celu_minimalnego)
            
            if L_poziom_celu_ostatecznego is None:
                L_poziom_celu_ostatecznego = L_poziom_celu_bazowego

            strefa = L_poziom_celu_bazowego - L_poziom_celu_minimalnego
            mod_proc = 0.0
            
            if WLACZ_MOD_CZAS_OGOLNY:
                dur = (timestamp - L_timestamp_otwarcia) / interval_ms if interval_ms else 0
                avg_min = L_suma_minut_w_pozycjach / L_licznik_zamknietych_pozycji if L_licznik_zamknietych_pozycji > 0 else 0.0
                avg_bars = avg_min / m_sw if m_sw > 0 else 9999
                if dur > avg_bars and avg_bars > 0:
                    mod_proc -= SILA_SPADKU_CZAS_OGOLNY
                    
            if WLACZ_MOD_CZAS_W_ZYSKU:
                wym_bars = math.ceil(CZAS_AKTYWACJI_W_ZYSKU / m_sw) if m_sw > 0 else 9999
                spelniony = True
                # look back wym_bars
                for b_j in range(max(0, len(linia_history) - wym_bars), len(linia_history)):
                    if not (linia_history[b_j] > L_poziom_niebieskiej_linii):
                        spelniony = False
                        break
                if spelniony:
                    mod_proc -= SILA_SPADKU_CZAS_W_ZYSKU
                    
            if WLACZ_MOD_WIELKOSC:
                total_k = sum(L_wartosci_linii)
                if total_k > PROG_KONTRAKTOW_MOD:
                    mod_proc -= (total_k - PROG_KONTRAKTOW_MOD) * SILA_SPADKU_MOD_WIELKOSC
            
            if strefa > 0:
                L_poziom_celu_ostatecznego += (strefa * (mod_proc / 100.0))
            L_poziom_celu_ostatecznego = max(L_poziom_celu_ostatecznego, L_poziom_celu_minimalnego)

        # CLOSE LONG
        if L_system_aktywny and pierwszy_czerwony and (linia > L_poziom_celu_ostatecznego) and not is_live_candle:
            dolki_final = L_licznik_nowych_dolkow # approx of [1]
            duration = (timestamp - L_timestamp_otwarcia) / interval_ms if interval_ms else 0
            L_licznik_zamknietych_pozycji += 1
            L_suma_wszystkich_dolkow += dolki_final
            L_suma_minut_w_pozycjach += duration * m_sw
            il_usr = len(L_poziomy_linii) - 1
            L_max_ilosc_usrednien = max(L_max_ilosc_usrednien, il_usr)
            
            markers.append({
                "time": ts_sec,
                "position": "aboveBar",
                "color": "#4caf50",
                "shape": "arrowDown",
                "text": "ZAMKNIĘCIE\nLONG"
            })
            
            L_system_aktywny = False
            L_poziomy_linii = []
            L_wartosci_linii = []
            L_najnizszy_dolek = None
            L_licznik_nowych_dolkow = 0
            L_poziom_niebieskiej_linii = None
            L_najnizszy_pnl_w_pozycji = 0.0
            L_poziom_celu_ostatecznego = None

            closed_trades.append({
                "type": 1,
                "entry_time": L_timestamp_otwarcia,
                "exit_time": timestamp,
                "averagings": il_usr,
                "profit": L_biezacy_pnl,
                "duration_min": duration * m_sw
            })


        # ---------------------------------------------------------
        # SHORT STRATEGY
        # ---------------------------------------------------------
        if pierwszy_czerwony and not is_live_candle:
            if not S_system_aktywny:
                S_system_aktywny = True
                S_timestamp_otwarcia = timestamp
                S_najwyzszy_szczyt = linia
                S_licznik_nowych_szczytow = 0
                S_poziomy_linii.append(linia)
                S_wartosci_linii.append(1.0)
                
                markers.append({
                    "time": ts_sec,
                    "position": "aboveBar",
                    "color": "#961414",
                    "shape": "arrowDown",
                    "text": "S_Otwarcie\n(waga: 1)"
                })
            else:
                gora_nowego_bloczku = linia + krok
                najwyzsza_istniejaca = max(S_poziomy_linii) if S_poziomy_linii else linia
                if gora_nowego_bloczku > najwyzsza_istniejaca and not is_live_candle:
                    S_poziomy_linii.append(linia)
                    qty_trend = max(1.0, float(S_licznik_nowych_szczytow))
                    S_wartosci_linii.append(qty_trend)
                    
                    markers.append({
                        "time": ts_sec,
                        "position": "aboveBar",
                        "color": "#640a0a",
                        "shape": "arrowDown",
                        "text": f"S_Uśrednienie\n(waga: {int(qty_trend)})"
                    })

        if S_system_aktywny:
            if trend == 1:
                if S_najwyzszy_szczyt is None or (linia > S_najwyzszy_szczyt):
                    S_najwyzszy_szczyt = linia
                    S_licznik_nowych_szczytow += 1
            
            if len(S_wartosci_linii) > 0:
                przychod_short = sum([S_poziomy_linii[j] * (S_wartosci_linii[j] * mnoznik_qty_short * LTC_NA_KONTRAKT) for j in range(len(S_poziomy_linii))])
                total_ltc = sum(S_wartosci_linii) * mnoznik_qty_short * LTC_NA_KONTRAKT
                
                # Use high_price instead of close_price to calculate worst-case PNL during candle
                koszt_odkupienia_worst_case = total_ltc * high_price
                S_biezacy_pnl_worst_case = przychod_short - koszt_odkupienia_worst_case
                S_najnizszy_pnl_w_pozycji = min(S_najnizszy_pnl_w_pozycji, S_biezacy_pnl_worst_case)
                S_biezacy_pnl = przychod_short - (total_ltc * close_price) # Actual PNL for panel

        if S_system_aktywny and len(S_poziomy_linii) > 0:
            suma_iloczynow = sum([S_poziomy_linii[j] * S_wartosci_linii[j] for j in range(len(S_poziomy_linii))])
            suma_wag = sum(S_wartosci_linii)
            S_poziom_niebieskiej_linii = suma_iloczynow / suma_wag
            S_poziom_celu_minimalnego = S_poziom_niebieskiej_linii * (1 - MINIMALNY_ZYSK_PROC_CELU / 100.0)
            
            total_ltc = sum(S_wartosci_linii) * mnoznik_qty_short * LTC_NA_KONTRAKT
            strata_na_jednostke = abs(S_najnizszy_pnl_w_pozycji) / total_ltc if total_ltc > 0 else 0
            cel_z_pnl = S_poziom_niebieskiej_linii - (strata_na_jednostke * 2)
            S_poziom_celu_bazowego = min(cel_z_pnl, S_poziom_celu_minimalnego)
            
            if S_poziom_celu_ostatecznego is None:
                S_poziom_celu_ostatecznego = S_poziom_celu_bazowego

            strefa = S_poziom_celu_minimalnego - S_poziom_celu_bazowego
            mod_proc = 0.0
            
            if WLACZ_MOD_CZAS_OGOLNY:
                dur = (timestamp - S_timestamp_otwarcia) / interval_ms if interval_ms else 0
                avg_min = S_suma_minut_w_pozycjach / S_licznik_zamknietych_pozycji if S_licznik_zamknietych_pozycji > 0 else 0.0
                avg_bars = avg_min / m_sw if m_sw > 0 else 9999
                if dur > avg_bars and avg_bars > 0:
                    mod_proc -= SILA_SPADKU_CZAS_OGOLNY
                    
            if WLACZ_MOD_CZAS_W_ZYSKU:
                wym_bars = math.ceil(CZAS_AKTYWACJI_W_ZYSKU / m_sw) if m_sw > 0 else 9999
                spelniony = True
                for b_j in range(max(0, len(linia_history) - wym_bars), len(linia_history)):
                    if not (linia_history[b_j] < S_poziom_niebieskiej_linii):
                        spelniony = False
                        break
                if spelniony:
                    mod_proc -= SILA_SPADKU_CZAS_W_ZYSKU
                    
            if WLACZ_MOD_WIELKOSC:
                total_k = sum(S_wartosci_linii)
                if total_k > PROG_KONTRAKTOW_MOD:
                    mod_proc -= (total_k - PROG_KONTRAKTOW_MOD) * SILA_SPADKU_MOD_WIELKOSC
            
            if strefa > 0:
                S_poziom_celu_ostatecznego += (strefa * (abs(mod_proc) / 100.0))
            S_poziom_celu_ostatecznego = min(S_poziom_celu_ostatecznego, S_poziom_celu_minimalnego)

        # CLOSE SHORT
        if S_system_aktywny and pierwszy_zielony and (linia < S_poziom_celu_ostatecznego) and not is_live_candle:
            szczyty_final = S_licznik_nowych_szczytow
            duration = (timestamp - S_timestamp_otwarcia) / interval_ms if interval_ms else 0
            S_licznik_zamknietych_pozycji += 1
            S_suma_wszystkich_szczytow += szczyty_final
            S_suma_minut_w_pozycjach += duration * m_sw
            il_usr = len(S_poziomy_linii) - 1
            S_max_ilosc_usrednien = max(S_max_ilosc_usrednien, il_usr)
            
            markers.append({
                "time": ts_sec,
                "position": "belowBar",
                "color": "#f44336",
                "shape": "arrowUp",
                "text": "ZAMKNIĘCIE\nSHORT"
            })
            
            S_system_aktywny = False
            S_poziomy_linii = []
            S_wartosci_linii = []
            S_najwyzszy_szczyt = None
            S_licznik_nowych_szczytow = 0
            S_poziom_niebieskiej_linii = None
            S_najnizszy_pnl_w_pozycji = 0.0
            S_poziom_celu_ostatecznego = None

            closed_trades.append({
                "type": -1,
                "entry_time": S_timestamp_otwarcia,
                "exit_time": timestamp,
                "averagings": il_usr,
                "profit": S_biezacy_pnl,
                "duration_min": duration * m_sw
            })


        # Append point for this candle
        results.append({
            "time": ts_sec, 
            "value": linia,
            "trend": trend,
            "L_cel": L_poziom_celu_ostatecznego if L_system_aktywny else None,
            "S_cel": S_poziom_celu_ostatecznego if S_system_aktywny else None,
            "L_blue": L_poziom_niebieskiej_linii if L_system_aktywny else None,
            "S_blue": S_poziom_niebieskiej_linii if S_system_aktywny else None
        })
        
    # Generate the panel text at the end
    sredni_wolumen_100 = f_oblicz_sredni_wolumen(candles, len(candles)-1, period=100)
    
    L_status = "AKTYWNY" if L_system_aktywny else "BRAK"
    L_total_ltc = sum(L_wartosci_linii) * mnoznik_qty_long * LTC_NA_KONTRAKT
    L_current_usr = len(L_poziomy_linii) - 1 if L_system_aktywny and len(L_poziomy_linii) > 0 else 0
    S_status = "AKTYWNY" if S_system_aktywny else "BRAK"
    S_total_ltc = sum(S_wartosci_linii) * mnoznik_qty_short * LTC_NA_KONTRAKT
    S_current_usr = len(S_poziomy_linii) - 1 if S_system_aktywny and len(S_poziomy_linii) > 0 else 0
    
    panel_text = {
        "L_status": L_status,
        "L_poz": round(L_total_ltc * 100, 2),
        "L_pnl": round(L_biezacy_pnl, 2),
        "L_usr": L_current_usr,
        "L_avg_usr": round(L_suma_wszystkich_dolkow / L_licznik_zamknietych_pozycji, 2) if L_licznik_zamknietych_pozycji > 0 else 0,
        "S_status": S_status,
        "S_poz": round(S_total_ltc * 100, 2),
        "S_pnl": round(S_biezacy_pnl, 2),
        "S_usr": S_current_usr,
        "S_avg_usr": round(S_suma_wszystkich_szczytow / S_licznik_zamknietych_pozycji, 2) if S_licznik_zamknietych_pozycji > 0 else 0,
        "vol": round(sredni_wolumen_100, 2)
    }

    # Limit list sizes to prevent memory leak in state but keep enough for `wym_bars` backwards lookups
    if len(linia_history) > 300: linia_history = linia_history[-300:]
    if len(trend_history) > 300: trend_history = trend_history[-300:]
    
    final_state = {
        'linia': linia, 'trend': trend, 'linia_history': linia_history, 'trend_history': trend_history,
        'L_system_aktywny': L_system_aktywny, 'L_poziomy_linii': L_poziomy_linii, 'L_wartosci_linii': L_wartosci_linii,
        'L_najnizszy_dolek': L_najnizszy_dolek, 'L_licznik_nowych_dolkow': L_licznik_nowych_dolkow,
        'L_timestamp_otwarcia': L_timestamp_otwarcia, 'L_poziom_niebieskiej_linii': L_poziom_niebieskiej_linii,
        'L_poziom_celu_minimalnego': L_poziom_celu_minimalnego, 'L_poziom_celu_bazowego': L_poziom_celu_bazowego,
        'L_poziom_celu_ostatecznego': L_poziom_celu_ostatecznego, 'L_biezacy_pnl': L_biezacy_pnl,
        'L_najnizszy_pnl_w_pozycji': L_najnizszy_pnl_w_pozycji, 'L_suma_wszystkich_dolkow': L_suma_wszystkich_dolkow,
        'L_licznik_zamknietych_pozycji': L_licznik_zamknietych_pozycji, 'L_suma_minut_w_pozycjach': L_suma_minut_w_pozycjach,
        'L_max_ilosc_usrednien': L_max_ilosc_usrednien,
        
        'S_system_aktywny': S_system_aktywny, 'S_poziomy_linii': S_poziomy_linii, 'S_wartosci_linii': S_wartosci_linii,
        'S_najwyzszy_szczyt': S_najwyzszy_szczyt, 'S_licznik_nowych_szczytow': S_licznik_nowych_szczytow,
        'S_timestamp_otwarcia': S_timestamp_otwarcia, 'S_poziom_niebieskiej_linii': S_poziom_niebieskiej_linii,
        'S_poziom_celu_minimalnego': S_poziom_celu_minimalnego, 'S_poziom_celu_bazowego': S_poziom_celu_bazowego,
        'S_poziom_celu_ostatecznego': S_poziom_celu_ostatecznego, 'S_biezacy_pnl': S_biezacy_pnl,
        'S_najnizszy_pnl_w_pozycji': S_najnizszy_pnl_w_pozycji, 'S_suma_wszystkich_szczytow': S_suma_wszystkich_szczytow,
        'S_licznik_zamknietych_pozycji': S_licznik_zamknietych_pozycji, 'S_suma_minut_w_pozycjach': S_suma_minut_w_pozycjach,
        'S_max_ilosc_usrednien': S_max_ilosc_usrednien
    }
    
    return results, markers, panel_text, closed_trades, final_state
