import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, filters, ContextTypes
from web3 import Web3
from cryptography.fernet import Fernet

# --- CONEXIÓN WEB3 (RED BASE MAINNET) ---
RPC_URL = "https://mainnet.base.org"
w3 = Web3(Web3.HTTPProvider(RPC_URL))

# ABI Mínimo estándar ERC-20
ERC20_ABI = [
    {"constant": True, "inputs": [], "name": "name", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"},
    {"constant": True, "inputs": [], "name": "symbol", "outputs": [{"name": "", "type": "string"}], "payable": False, "stateMutability": "view", "type": "function"}
]

# --- CONFIGURACIÓN DE SEGURIDAD CRIPTOGRÁFICA ---
MASTER_KEY = os.environ.get("ENCRYPTION_KEY")
if not MASTER_KEY:
    MASTER_KEY = Fernet.generate_key().decode()

cipher_suite = Fernet(MASTER_KEY.encode())

# Base de datos local para almacenar usuarios y referidos
USER_DATABASE = {}

DEV_WALLET = "0xe9903588E2Ff2CF5Bd847eE375b765F14B59bce3"
PARTNER_WALLET = os.environ.get("PARTNER_WALLET", "0x0000000000000000000000000000000000000000")

def inicializar_usuario_si_no_existe(user_id, referido_por=None):
    if user_id not in USER_DATABASE:
        new_account = w3.eth.account.create()
        clave_privada_bytes = new_account.key.hex().encode()
        clave_encriptada = cipher_suite.encrypt(clave_privada_bytes).decode()
        
        USER_DATABASE[user_id] = {
            "address": new_account.address,
            "encrypted_private_key": clave_encriptada,
            "auto_buy": False,
            "auto_buy_amount": 0.05,
            "referido_por": referido_por,
            "contador_referidos": 0
        }
        
        if referido_por and referido_por in USER_DATABASE:
            USER_DATABASE[referido_por]["contador_referidos"] += 1

def obtener_balance_real(address):
    try:
        balance_wei = w3.eth.get_balance(address)
        return w3.from_wei(balance_wei, 'ether')
    except Exception:
        return 0.0

def calcular_triple_split_comision(amount_in_eth, tiene_padrino=False):
    amount_in_wei = w3.to_wei(amount_in_eth, 'ether')
    total_fee_wei = int(amount_in_wei * 0.01)
    
    if tiene_padrino:
        share_referente_wei = int(total_fee_wei * 0.20)
        share_socios_wei = (total_fee_wei - share_referente_wei) // 2
        remaining_amount_wei = amount_in_wei - total_fee_wei
        return {
            "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
            "dev_share_eth": w3.from_wei(share_socios_wei, 'ether'),
            "partner_share_eth": w3.from_wei(share_socios_wei, 'ether'),
            "referral_share_eth": w3.from_wei(share_referente_wei, 'ether'),
            "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether')
        }
    else:
        share_each_wei = total_fee_wei // 2
        remaining_amount_wei = amount_in_wei - total_fee_wei
        return {
            "total_fee_eth": w3.from_wei(total_fee_wei, 'ether'),
            "dev_share_eth": w3.from_wei(share_each_wei, 'ether'),
            "partner_share_eth": w3.from_wei(share_each_wei, 'ether'),
            "referral_share_eth": 0.0,
            "remaining_eth": w3.from_wei(remaining_amount_wei, 'ether')
        }

# --- MENÚS DE INTERFAZ ---
def generar_menu_principal(user_id):
    user_data = USER_DATABASE[user_id]
    wallet_address = user_data["address"]
    balance = obtener_balance_real(wallet_address)
    wallet_corta = f"{wallet_address[:6]}...{wallet_address[-4:]}"
    status_sniper = "🟢 Activo" if user_data["auto_buy"] else "🔴 Inactivo"
    
    texto = (
        f"🦅 *BASE TRADING ENGINE*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"💳 *Wallet:* `{wallet_corta}`\n"
        f"💰 *Balance:* `{balance:.4f} ETH`\n"
        f"🎯 *Modo Sniper:* {status_sniper}\n\n"
        f"─── — — — — — — — — — ───\n"
        f"⚡ *¿Cómo empezar a operar?*\n"
        f"Pega el contrato de cualquier token de Base aquí abajo para analizar su liquidez."
    )
    
    keyboard = [
        [InlineKeyboardButton("🔄 Actualizar Balance", callback_data="back_main")],
        [
            InlineKeyboardButton("📥 Depositar", callback_data="ver_wallet"),
            InlineKeyboardButton("📤 Retirar", callback_data="retirar_fondos")
        ],
        [
            InlineKeyboardButton("👥 Sistema de Referidos", callback_data="ver_referidos"),
            InlineKeyboardButton("⚙️ Configuración", callback_data="abrir_settings")
        ]
    ]
    return texto, InlineKeyboardMarkup(keyboard)

def generar_menu_referidos(user_id, bot_username):
    user_data = USER_DATABASE[user_id]
    cant_referidos = user_data["contador_referidos"]
    link_referido = f"https://t.me/{bot_username}?start={user_id}"
    
    texto_referidos = (
        f"👥 *SISTEMA DE REFERIDOS ON-CHAIN*\n"
        f"─── — — — — — — — — — ───\n\n"
        f"¡Genera ingresos pasivos invitando a otros a operar!\n\n"
        f"📈 *Tu Impacto Comercial:*\n"
        f"• Amigos invitados: `{cant_referidos}`\n"
        f"• Tu comisión: *20% del peaje (0.2% neto de cada swap)*\n\n"
        f"🔗 *Tu Enlace Único de Invitación:*\n"
        f"`{link_referido}`"
    )
    keyboard = [[InlineKeyboardButton("⬅️ Volver al Panel Principal", callback_data="back_main")]]
    return texto_referidos, InlineKeyboardMarkup(keyboard)

def generar_menu_settings(user_id):
    user_data = USER_DATABASE[user_id]
    status_emoji = "🟢 ACTIVADO" if user_data["auto_buy"] else "🔴 DESACTIVADO"
    monto = user_data["auto_buy_amount"]
    
    texto_settings = (
        f"⚙️ *PANEL DE CONFIGURACIÓN*\n\n"
        f"🚀 *Compra Automática (Auto-Buy):* `{status_emoji}`\n"
        f"💵 *Monto por Defecto:* `{monto} ETH`\n"
        f"🔒 *Seguridad:* Encriptado simétrico AES-256"
    )
    keyboard = [
        [
            InlineKeyboardButton("🎯 Alternar Auto-Buy", callback_data="toggle_autobuy"),
            InlineKeyboardButton
