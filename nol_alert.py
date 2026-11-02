"""NOL 티켓 잔여석 감시 → 텔레그램 알림. 예매는 직접 합니다.

사용법:
  python nol_alert.py            감시 시작
  python nol_alert.py --test     텔레그램 테스트 메시지만 보내기
  python nol_alert.py --selftest 판정 로직 점검
"""
import json, os, random, sys, time, urllib.parse, urllib.request
from pathlib import Path

GOODS = "26015024"                 # 공연 상품 번호 (주소 끝 숫자)
PLAY_SEQS = {"001": "1/14(목) 19:30", "002": "1/16(토) 19:00", "003": "1/17(일) 19:00"}
INTERVAL = 30                      # 초. 너무 줄이면 차단될 수 있음
PAGE = f"https://nol.yanolja.com/ticket/products/{GOODS}"
API = "https://nol.yanolja.com/ticket/products/api/remaining-seats?goodsCode={}&playSeq={}"
CONF = Path(__file__).with_name("config.json")  # {"token": "...", "chat_id": ""}
UA = {"User-Agent": "Mozilla/5.0"}


def get_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=15) as r:
        return json.load(r)


def tg(conf, method, **params):
    url = f"https://api.telegram.org/bot{conf['token']}/{method}"
    with urllib.request.urlopen(url, data=urllib.parse.urlencode(params).encode(), timeout=15) as r:
        return json.load(r)


def load_conf():
    if os.environ.get("TG_TOKEN"):  # GitHub Actions: 비밀값에서 읽음
        return {"token": os.environ["TG_TOKEN"], "chat_id": os.environ["TG_CHAT_ID"]}
    conf = json.loads(CONF.read_text(encoding="utf-8"))
    if ":" not in conf.get("token", ""):
        sys.exit("config.json에 봇 토큰이 없어요. BotFather가 준 토큰(숫자:영문 형태)을 넣고 저장하세요.")
    if not conf.get("chat_id"):
        # 봇에게 먼저 아무 말이나 보내 둬야 여기서 찾을 수 있음
        ups = [u for u in tg(conf, "getUpdates")["result"] if "message" in u]
        if not ups:
            sys.exit("chat_id를 못 찾았어요. 텔레그램에서 봇에게 아무 메시지나 보낸 뒤 다시 실행하세요.")
        conf["chat_id"] = str(ups[-1]["message"]["chat"]["id"])
        CONF.write_text(json.dumps(conf, ensure_ascii=False, indent=2), encoding="utf-8")
    return conf


def open_seats(data):
    """잔여석이 있는 (등급, 개수) 목록."""
    return [(s["seatGradeName"], s["remainCnt"]) for s in data.get("remainSeat", []) if s.get("remainCnt", 0) > 0]


def send(conf, text):
    tg(conf, "sendMessage", chat_id=conf["chat_id"], text=text)
    print(time.strftime("%H:%M:%S"), "알림:", text.splitlines()[0])


def main():
    conf = load_conf()
    if "--test" in sys.argv:
        send(conf, "테스트 메시지예요. 알림이 잘 옵니다.")
        return
    on_gh = bool(os.environ.get("GITHUB_ACTIONS"))
    end = time.time() + float(os.environ.get("RUN_MINUTES", "inf")) * 60
    if not on_gh:  # GitHub은 몇 분마다 새로 시작하므로 시작 알림 생략
        send(conf, f"감시 시작: {PAGE}\n{INTERVAL}초 간격으로 확인해요.")
    was_open = {seq: False for seq in PLAY_SEQS}
    fails = 0
    while time.time() < end:
        for seq, label in PLAY_SEQS.items():
            try:
                seats = open_seats(get_json(API.format(GOODS, seq)))
                fails = 0
            except Exception as e:
                fails += 1
                print(time.strftime("%H:%M:%S"), "조회 실패:", e)
                if fails == 10:  # 감시가 멈춘 걸 모르고 기다리지 않도록
                    send(conf, f"조회가 계속 실패하고 있어요 (차단됐을 수 있음): {e}")
                continue
            if seats and not was_open[seq]:  # 매진→풀림 순간에만 알림
                lines = "\n".join(f"- {g}: {n}석" for g, n in seats)
                send(conf, f"🎫 자리 풀림!{' [GitHub]' if on_gh else ''} {label}\n{lines}\n{PAGE}")
            was_open[seq] = bool(seats)
            time.sleep(2)
        print(time.strftime("%H:%M:%S"), "확인:", {PLAY_SEQS[s]: ("있음" if o else "매진") for s, o in was_open.items()})
        time.sleep(INTERVAL + random.uniform(0, 10))


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        assert open_seats({"remainSeat": [{"seatGradeName": "A", "remainCnt": 0}]}) == []
        assert open_seats({"remainSeat": [{"seatGradeName": "A", "remainCnt": 2}]}) == [("A", 2)]
        print("selftest ok")
    else:
        main()
