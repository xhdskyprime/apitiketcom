import json
import time
import sys
import logging

# Ensure UTF-8 output on Windows console
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass

from berburu_api import BerburuAPI

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_berburu.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("BotBerburu")

def load_config(config_path="config.json"):
    with open(config_path, "r", encoding="utf-8") as f:
        return json.load(f)

def run_war():
    config = load_config()
    auth_config = config.get("auth", {})
    berburu_config = config.get("berburu", {})
    
    campaign_id = berburu_config.get("campaign_id", "6a8341e6a61742e6257428dd")
    sniper_seconds = float(berburu_config.get("sniper_seconds", 1.0))
    check_interval_ms = float(berburu_config.get("check_interval_ms", 200)) / 1000.0
    auto_re_steal = berburu_config.get("auto_re_steal", True)
    max_token_usage = int(berburu_config.get("max_token_usage", 50))
    
    api = BerburuAPI(auth_config=auth_config)
    
    logger.info("==================================================")
    logger.info("   TIKET.COM BERBURU TIKET MURAH (HARTA KARUN) BOT  ")
    logger.info("==================================================")
    
    # 1. Fetch Player State
    player_state = api.get_player_state()
    if not player_state:
        logger.error("Gagal mendapatkan status player! Periksa cookie/session di config.json.")
        return
        
    my_player_id = player_state.get("playerId")
    token_balance = int(player_state.get("token", 0))
    logger.info(f"Player ID       : {my_player_id}")
    logger.info(f"Token Tersisa   : {token_balance}")
    logger.info(f"Sniper Seconds  : {sniper_seconds}s")
    logger.info(f"Check Interval  : {check_interval_ms*1000:.0f}ms")
    logger.info(f"Max Token Usage : {max_token_usage}")
    logger.info("--------------------------------------------------")
    
    tokens_used_this_run = 0
    last_hit_time = 0
    
    while True:
        try:
            prod = api.get_campaign_product(campaign_id)
            if not prod:
                logger.warning("Produk tidak ditemukan / error saat fetch product detail.")
                time.sleep(1)
                continue
                
            session_id = prod.get("sessionId")
            title = prod.get("title")
            subtitle = prod.get("subtitle")
            token_cost = int(prod.get("token", 3))
            price_info = prod.get("priceSettings", {})
            disc_price = price_info.get("discountedPrice", "0")
            orig_price = price_info.get("price", "0")
            
            countdown = prod.get("countDown", {})
            try:
                duration_left = float(countdown.get("durationLeftInSeconds", 999))
            except (ValueError, TypeError):
                duration_left = 999.0
                
            recent_subs = prod.get("recentSubmissions", [])
            latest_player_id = recent_subs[0].get("playerId") if recent_subs else None
            latest_username = recent_subs[0].get("username") if recent_subs else "N/A"
            
            is_me_leading = (latest_player_id == my_player_id)
            status_lead = "[AKUN KITA LEADING]" if is_me_leading else f"[DIPEGANG ORANG: {latest_username}]"
            
            logger.info(f"[{title}] Sisa: {duration_left:.1f}s | {status_lead} | Rp {disc_price} (Normal: Rp {orig_price})")
            
            # Sniper logic: Hit when timer is low and we're NOT leading
            if duration_left <= sniper_seconds and not is_me_leading:
                if token_balance < token_cost:
                    logger.warning(f"Token tidak cukup! Sisa token: {token_balance}, butuh: {token_cost}")
                    time.sleep(1)
                    continue
                    
                if tokens_used_this_run >= max_token_usage:
                    logger.warning(f"Batas penggunaan token ({max_token_usage}) telah tercapai.")
                    time.sleep(1)
                    continue
                    
                logger.info(f"[SNIPER TRIGGERED] Sisa waktu {duration_left:.1f}s <= {sniper_seconds}s! Menembak HIT...")
                success, res_data, server_time = api.hit_chest(session_id)
                last_hit_time = time.time()
                
                if success:
                    tokens_used_this_run += token_cost
                    token_balance -= token_cost
                    logger.info(f"[HIT SUCCESSFUL] Berhasil merebut Harta Karun! Total token terpakai: {tokens_used_this_run}, Sisa: {token_balance}")
                    logger.info(f"   Detail Response: {res_data}")
                else:
                    logger.error(f"[HIT FAILED] Respon: {res_data}")
                    
            elif auto_re_steal and not is_me_leading and duration_left > sniper_seconds:
                # If lost lead and cooldown passed
                if time.time() - last_hit_time > 3.0 and tokens_used_this_run < max_token_usage and token_balance >= token_cost:
                    logger.info(f"[AUTO RE-STEAL] Merebut kembali harta karun dari {latest_username}...")
                    success, res_data, server_time = api.hit_chest(session_id)
                    last_hit_time = time.time()
                    if success:
                        tokens_used_this_run += token_cost
                        token_balance -= token_cost
                        logger.info(f"[RE-STEAL SUCCESSFUL] Berhasil merebut kembali! Sisa token: {token_balance}")
            
            time.sleep(check_interval_ms)
            
        except KeyboardInterrupt:
            logger.info("Bot dihentikan oleh pengguna.")
            break
        except Exception as e:
            logger.exception(f"Error pada main loop: {e}")
            time.sleep(1)

if __name__ == "__main__":
    run_war()
