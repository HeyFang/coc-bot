import subprocess
import cv2
import numpy as np
import time
import random
from dotenv import load_dotenv
import os
import pytesseract

load_dotenv()

ADB = "adb"
DEVICE = os.getenv("DEVICE_ID")

if not DEVICE:
    raise ValueError("DEVICE_ID not set — copy .env.example to .env and add your device ID")



def adb(cmd):
    """Run any adb command"""
    return subprocess.run(
        [ADB, "-s", DEVICE] + cmd,
        capture_output=True
    )

def screenshot():
    result = adb(["exec-out", "screencap", "-p"])
    if not result.stdout:
        raise ConnectionError("ADB returned empty — check USB connection")
    img_array = np.frombuffer(result.stdout, dtype=np.uint8)
    img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
    if img is None:
        raise ConnectionError("Screenshot decoded as None")
    return img

def tap(x, y):
    """Basic tap — used internally"""
    adb(["shell", "input", "tap", str(x), str(y)])
    print(f"  → tapped ({x}, {y})")

def human_tap(x, y, radius=15):
    """Tap with random offset + random delay to simulate human"""
    rx = x + random.randint(-radius, radius)
    ry = y + random.randint(-radius, radius)
    adb(["shell", "input", "tap", str(rx), str(ry)])
    print(f"  → tapped ({rx}, {ry}) [target ({x}, {y})]")
    time.sleep(random.uniform(0.1, 0.4))

def save_screenshot(filename="screenshots/screen.png"):
    """Save screenshot to disk for inspection"""
    img = screenshot()
    if img is not None:
        cv2.imwrite(filename, img)
        print(f"  → saved to {filename}")
    else:
        print("  → ERROR: screenshot returned nothing, check ADB connection")
    return img

def crop_template(x, y, w, h, filename):
    """
    Crop a region from current screen and save as template
    x, y = top-left corner
    w, h = width and height
    """
    img = screenshot()
    crop = img[y:y+h, x:x+w]
    cv2.imwrite(f"templates/{filename}", crop)
    print(f"  → saved template: templates/{filename}")
    return crop

def find_template(template_path, threshold=0.8):
    """
    Find a template image on the current screen.
    Returns (x, y) center coordinates if found, None if not found.
    """
    screen = screenshot()
    template = cv2.imread(template_path)

    if template is None:
        print(f"  → ERROR: template not found at {template_path}")
        return None

    # Do the matching
    result = cv2.matchTemplate(screen, template, cv2.TM_CCOEFF_NORMED)

    # Get the best match score and location
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)

    print(f"  → match score: {max_val:.2f} (need >{threshold})")

    if max_val >= threshold:
        # max_loc is top-left corner, calculate center
        h, w = template.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        print(f"  → found at center: ({center_x}, {center_y})")
        return (center_x, center_y)
    else:
        print(f"  → not found on screen")
        return None

def find_and_tap(template_path, threshold=0.6):
    pos = find_template(template_path, threshold)
    if pos:
        time.sleep(random.uniform(0.1, 0.6))  # reaction time before tapping
        human_tap(pos[0], pos[1])
        return True
    return False

def wait_for_template(template_path, timeout=60, threshold=0.8):
    """Keep checking until template appears — with random poll interval"""
    print(f"  → waiting for {template_path}...")
    start = time.time()
    while time.time() - start < timeout:
        if find_template(template_path, threshold):
            return True
        time.sleep(random.uniform(1.5, 3.5))  # varied poll interval
    print(f"  → TIMEOUT waiting for {template_path}")
    return False

def human_sleep(min_s, max_s):
    """Random sleep between min and max seconds"""
    t = random.uniform(min_s, max_s)
    time.sleep(t)

def normalize_view():
    """Scroll to expose top-left deployment edge — with random variation"""
    scrolls_up = random.randint(2, 3)
    scrolls_left = random.randint(1, 3)

    for _ in range(scrolls_up):
        # Slightly randomize swipe start/end points
        sx = random.randint(650, 750)
        sy = random.randint(280, 320)
        ey = random.randint(520, 580)
        dur = random.randint(350, 500)
        adb(["shell", "input", "swipe", str(sx), str(sy), str(sx), str(ey), str(dur)])
        time.sleep(random.uniform(0.3, 0.6))

    for _ in range(scrolls_left):
        sx = random.randint(450, 550)
        sy = random.randint(320, 380)
        ex = random.randint(750, 850)
        dur = random.randint(350, 500)
        adb(["shell", "input", "swipe", str(sx), str(sy), str(ex), str(sy), str(dur)])
        time.sleep(random.uniform(0.3, 0.6))

    time.sleep(random.uniform(0.4, 0.8))


def find_red_zone_edge(scan_from_x=50, scan_to_x=800, scan_y_range=(50, 500)):
    """
    Detect the top-left edge of the red (no-deploy) zone.
    Scans columns from left to right, finds topmost red pixel in each column.
    Returns list of (x, y) points along the edge — just outside red zone.
    """
    screen = screenshot()
    edge_points = []

    for x in range(scan_from_x, scan_to_x, 25):
        for y in range(scan_y_range[0], scan_y_range[1]):
            b, g, r = screen[y][x]

            # Red zone detection — red channel dominant
            is_red_zone = (
                r > 150 and        # strong red
                r > g * 1.5 and    # much redder than green
                r > b * 1.5        # much redder than blue
            )

            if is_red_zone:
                # Step back 15px outside the red zone
                deploy_y = max(y - 15, 0)
                deploy_x = max(x - 15, 0)
                edge_points.append((deploy_x, deploy_y))
                break  # found topmost red in this column, move to next

    return edge_points

def deploy_clustered(edge_points, count=12, repeat=2):
    """
    Deploy troops in a cluster around the center of the edge.
    Drops each troop 'repeat' times to handle red zone misses.
    Adds human-like randomness to each tap.
    """
    if not edge_points:
        print("  → ERROR: no edge points")
        return

    # Focus on center 40% of the edge line for clustering
    center_start = len(edge_points) // 3
    center_end = 2 * len(edge_points) // 3
    cluster_points = edge_points[center_start:center_end]

    if not cluster_points:
        cluster_points = edge_points  # fallback to all points

    print(f"  → deploying in cluster of {len(cluster_points)} points")

    taps_done = 0
    target_taps = count * repeat  # e.g. 12 troops * 2 = 24 taps

    while taps_done < target_taps:
        # Pick a random point from cluster each time
        x, y = random.choice(cluster_points)
        human_tap(x, y)
        taps_done += 1
        # Random pause between troops like a human would
        time.sleep(random.uniform(0.15, 0.5))

    print(f"  → done ({taps_done} taps for {count} troops)")

def deploy_hero(icon_template, edge_points, repeats=3):
    """
    Select hero and tap deployment spot multiple times.
    Retries icon tap if not found.
    """
    # Try tapping icon up to 3 times
    for attempt in range(3):
        if find_and_tap(icon_template):
            break
        print(f"  → hero icon not found, retrying ({attempt+1}/3)...")
        time.sleep(0.5)

    time.sleep(random.uniform(0.3, 0.6))

    # Pick a point from center cluster, tap it multiple times
    center_start = len(edge_points) // 3
    center_end = 2 * len(edge_points) // 3
    cluster = edge_points[center_start:center_end]
    if not cluster:
        cluster = edge_points

    for _ in range(repeats):
        x, y = random.choice(cluster)
        human_tap(x, y, radius=20)
        time.sleep(random.uniform(0.2, 0.5))

def use_hero_abilities(edge_points):
    """
    Use hero abilities mid-battle by tapping hero icons again.
    Called ~30s after deployment when heroes are inside the base.
    """
    print("[Abilities] Activating hero abilities...")
    
    # Each hero ability is activated by tapping their portrait
    # which appears on screen during battle (bottom left area)
    for template in ["templates/king_icon.png", 
                     "templates/queen_icon.png",
                     "templates/warden_icon.png"]:
        result = find_and_tap(template, threshold=0.5)
        if result:
            print(f"  → ability used")
        else:
            print(f"  → hero not found/available")
        time.sleep(random.uniform(0.5, 1.0))

def visualize_edge(edge_points):
    """Draw detected edge points on screenshot for verification"""
    screen = screenshot()
    for (x, y) in edge_points:
        cv2.circle(screen, (x, y), 8, (255, 0, 0), -1)  # blue dots
    cv2.imwrite("screenshots/edge_debug.png", screen)
    print(f"  → found {len(edge_points)} edge points")


def run_attack():
    """Single full attack cycle"""

    # --- STATE 1: Home Village ---
    print("\n[State 1] Tapping Attack...")
    if not find_and_tap("templates/attack_btn.png"):
        print("  → Attack button not found!")
        return False
    human_sleep(1.5, 3.0)  # ← was time.sleep(2)

    # --- STATE 2: Battle Menu ---
    print("[State 2] Tapping Find a Match...")
    if not find_and_tap("templates/find_match_btn.png"):
        print("  → Find a Match not found!")
        return False
    human_sleep(1.5, 3.0)  # ← was time.sleep(2)

    # --- STATE 3: Army Confirmation ---
    print("[State 3] Confirming army...")
    if not find_and_tap("templates/confirm_attack_btn.png"):
        print("  → Confirm Attack not found!")
        return False
    human_sleep(6, 10)  # ← matchmaking wait, varied

     # --- STATE 4: Enemy Base — Loot Check ---
    # GOLD_MIN   = 400_000
    ELIXIR_MIN = 400_000
    DARK_MIN   = 4_000
    MAX_SKIPS = 15  # don't skip forever, give up after this many
    skips = 0

    while skips < MAX_SKIPS:
        print(f"[State 4] Checking loot (skip #{skips})...")
        gold, elixir, dark = read_loot()

        if gold >= GOLD_MIN or elixir >= ELIXIR_MIN or dark >= DARK_MIN:
            print(f"  → loot good! attacking...")
            break  # exit loop and attack

        print(f"  → loot too low (gold:{gold:,} elixir:{elixir:,} dark:{dark:,}), skipping...")
        find_and_tap("templates/next_btn.png")
        human_sleep(4, 7)  # wait for NEW base to fully load before re-reading
        skips += 1
    else:
        # Exhausted all skips without finding good loot
        print(f"  → gave up after {MAX_SKIPS} skips, ending battle...")
        find_and_tap("templates/end_battle_btn.png")
        human_sleep(2, 4)
        find_and_tap("templates/return_home_btn.png")
        human_sleep(4, 7)
        return False



    while gold < GOLD_MIN or elixir < ELIXIR_MIN or dark < DARK_MIN:
        print(f"  → loot too low (gold:{gold:,} elixir:{elixir:,}), skipping...")
        find_and_tap("templates/next_btn.png")
        human_sleep(3, 5)  # wait for next base to load
        
    
    print(f"  → loot good! (gold:{gold:,} elixir:{elixir:,}), attacking...")
    print("[State 4] Normalizing view...")
    normalize_view()
    human_sleep(0.8, 1.5)

    print("[State 4] Detecting red zone edge...")
    edge_points = find_red_zone_edge()
    print(f"  → {len(edge_points)} edge points found")

    if not edge_points:
        print("  → no edge detected, tapping Next...")
        find_and_tap("templates/next_btn.png")
        return False

    visualize_edge(edge_points)

    # Deploy dragons
    print("[State 4] Deploying dragons...")
    find_and_tap("templates/dragon_icon.png")
    human_sleep(0.4, 0.8)
    deploy_clustered(edge_points, count=16, repeat=1)
    human_sleep(0.3, 1)

    # Deploy heroes
    print("[State 4] Deploying heroes...")
    deploy_hero("templates/king_icon.png", edge_points, repeats=3)
    human_sleep(0.4, 0.9)
    deploy_hero("templates/queen_icon.png", edge_points, repeats=3)
    human_sleep(0.4, 0.9)
    deploy_hero("templates/warden_icon.png", edge_points, repeats=3)
    human_sleep(0.5, 1.2)

    # Wait for heroes to enter base then use abilities
    print("[State 4] Waiting for heroes to enter base...")
    human_sleep(5, 15)
    use_hero_abilities(edge_points)

    # --- STATE 5: Wait for battle ---
    print("[State 5] Waiting for battle to finish...")
    if not wait_for_template("templates/return_home_btn.png", timeout=240):
        print("  → battle timed out")
        return False

    # --- STATE 6: Results ---
    print("[State 6] Tapping Return Home...")
    human_sleep(0.5, 1.5)  # brief pause before tapping, like a human reading results
    find_and_tap("templates/return_home_btn.png")
    human_sleep(4, 7)  # wait for home village to load

    return True

def idle_behavior():
    """
    Occasionally do nothing or random scroll on home screen.
    Makes the bot look like a human who pauses to think.
    """
    behavior = random.choice(["pause", "scroll", "double_pause"])
    
    if behavior == "pause":
        t = random.uniform(15, 40)
        print(f"  → idling for {t:.0f}s")
        time.sleep(t)
    
    elif behavior == "scroll":
        t = random.uniform(8, 20)
        print(f"  → idle scrolling for {t:.0f}s")
        time.sleep(t)
        adb(["shell", "input", "swipe",
             str(random.randint(400, 800)),
             str(random.randint(200, 400)),
             str(random.randint(400, 800)),
             str(random.randint(200, 400)),
             str(random.randint(300, 700))])
        time.sleep(random.uniform(3, 8))  # pause after scroll
    
    elif behavior == "double_pause":
        time.sleep(random.uniform(20, 40))

def read_loot():
    """
    Crop the loot region and OCR the gold and elixir values.
    Returns (gold, elixir) as integers, or (0, 0) if reading fails.
    """
    screen = screenshot()

    # Crop each loot value individually
    # Format: screen[y1:y2, x1:x2]
    gold_crop    = screen[95:125,  105:230]
    elixir_crop  = screen[130:160, 105:230]
    dark_crop    = screen[170:200, 105:230]

    # Upscale for better OCR accuracy — tesseract likes larger text
    def upscale(img, scale=2):
        h, w = img.shape[:2]
        return cv2.resize(img, (w * scale, h * scale), interpolation=cv2.INTER_LINEAR)

    # Convert to grayscale + threshold to make text crisp
    def preprocess(img):
        img = upscale(img, scale=3)
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # cv2.threshold returns (retval, thresholded_image) — unpack correctly
        _, thresh = cv2.threshold(gray, 160, 255, cv2.THRESH_BINARY)
        return thresh  # return only the image, not the tuple

    # OCR config — digits only, single line
    config = "--psm 7 -c tessedit_char_whitelist=0123456789"

    def ocr_number(crop, debug_name=None):
        processed = preprocess(crop)
        if debug_name:
            cv2.imwrite(f"screenshots/ocr_{debug_name}.png", processed)
        
        # Convert OpenCV image to PIL for pytesseract
        from PIL import Image
        pil_img = Image.fromarray(processed)
        
        config = "--oem 3 --psm 7 -c tessedit_char_whitelist=0123456789"
        text = pytesseract.image_to_string(pil_img, config=config)
        cleaned = text.strip().replace(" ", "").replace(",", "").replace(".", "")
        try:
            return int(cleaned)
        except ValueError:
            print(f"  → OCR failed to parse: '{text.strip()}'")
            return 0
    gold   = ocr_number(gold_crop,   debug_name="gold")
    elixir = ocr_number(elixir_crop, debug_name="elixir")
    dark   = ocr_number(dark_crop,   debug_name="dark")

    print(f"  → Gold:        {gold:,}")
    print(f"  → Elixir:      {elixir:,}")
    print(f"  → Dark Elixir: {dark:,}")

    return gold, elixir, dark

# if __name__ == "__main__":
#     save_screenshot()
#     crop_template(x=350, y=620, w=70, h=85, filename="switch_icon.png")


#--- MAIN LOOP ---
if __name__ == "__main__":
    attack_count = 0
    max_attacks = random.randint(15, 20)  # vary the session length too
    session_start = time.time()
    max_session_hours = random.uniform(1.5, 3.0)  # bot for 1.5-3hrs then stop

    print("=== COC BOT STARTING ===")
    print(f"Session limit: {max_session_hours:.1f} hours, max {max_attacks} attacks\n")

    while attack_count < max_attacks:
        # Check session time limit
        elapsed_hours = (time.time() - session_start) / 3600
        if elapsed_hours >= max_session_hours:
            print(f"\n[Session] Time limit reached ({elapsed_hours:.1f}h), stopping.")
            break

        attack_count += 1
        print(f"\n{'='*40}")
        print(f"ATTACK #{attack_count} | Session: {elapsed_hours:.1f}h/{max_session_hours:.1f}h")
        print(f"{'='*40}")

        success = run_attack()

        if success:
            print(f"  ✓ Attack #{attack_count} completed!")
        else:
            print(f"  ✗ Attack #{attack_count} had issues")
            human_sleep(3, 8)

        idle_behavior()

    print(f"\n=== BOT FINISHED === {attack_count} attacks in {elapsed_hours:.1f}h") 






