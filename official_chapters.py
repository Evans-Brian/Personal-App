"""Official BJJ Fanatics chapter titles and start times."""

OFFICIAL_CHAPTERS = {
    "down-right-sloppy-half-butterfly": [
        [("Intro", "0:00"), ("Positioning", "0:36"), ("Dealing with negative partners", "3:09"), ("Dealing with partners arm weave knee smashed", "6:02"), ("Dealing with partners arm weave knee not smashed", "8:56"), ("Dealing with partner hugging thigh", "13:12"), ("Dealing with partner wrist grip", "19:35"), ("Arm drag left side", "25:46"), ("Knee lever", "28:55")],
        [("Arm saddle", "0:00"), ("Arm saddle hand fighting Scoop grip vs sprawl", "2:42"), ("Arm saddle hand fighting off scoop grip partner cross faces", "8:22"), ("Shoulder crunch sweep against partner driving in", "15:54"), ("Arm saddle hand fighting vs wrist grab", "19:31"), ("Arm saddle hand fighting vs low posture", "21:56"), ("Arm saddle hand fighting vs thumb post in shoulder", "24:03"), ("Shoulder crunch/choi bar which to use", "26:06"), ("Partner denies forearm in front of face 100%er", "31:51")],
        [("Kimura", "0:00"), ("Backtake", "6:19"), ("Leg assisted kimura", "9:55"), ("Triangle", "12:48"), ("Invert to back", "16:58"), ("Shotgun armlock", "19:57")],
        [("Leg entries - Scoop entry to saddle with thumb post", "0:00"), ("Scoop grip leg entry to Underhook x with lat post", "4:25"), ("Leg entry to saddle", "8:09"), ("Dealing with partner Shin staple", "13:59"), ("Dealing with partner shin staple and sprawl", "17:17"), ("Counter Backstep defense", "20:27"), ("K guard entry against counter backstep", "22:11"), ("Boston crab", "25:32"), ("Conclusion", "28:19")],
    ],
    "octopus-guard-2": [
        [("Craig The King Jones and Hey She's Hotter", "0:00"), ("Half Guard Vs Side Control", "4:35"), ("Jiu Jitsu VS Wrestling Cross Face", "11:33"), ("Side Control Is Not Real", "15:06"), ("The Only Grips You'll Ever Need", "20:38"), ("Piss Like A Dog", "26:41"), ('The Modern "Technical Get The F**K Up"', "32:00")],
        [("Sweep Them Off Their Feet", "0:00"), ("Get Them When They're Vulnerable", "5:48"), ("Why You're Fat? And Yo Makikomi Roll Still Don't Work", "10:42"), ("Switch Hipper Counter", "15:00"), ("Dealing With Reverse - Side Control", "23:13"), ("Darce Chokes Are Fake", "30:07"), ("The Infamous Darce Counter Back Take", "35:13"), ("Teach Me How To Buggy - Off The Darce", "38:30")],
        [("Wrist Ride Buggy", "0:00"), ("Vintage Buggy", "5:50"), ("Buggy Choke To Ghost Darce", "11:13"), ("Front Head Ain't No Thang", "14:12"), ("Darce Grip Break", "17:45"), ("Peak Out Counter To Darce", "21:29"), ("Don't Forget Their Legs", "24:07"), ("Turtle Over Wrap", "27:27"), ("Turtle Over Wrap: Armbar And Triangle", "33:48")],
        [("Turtle Overwrap: Leg Attacks", "0:00"), ("Crucifix = Fireman's Carry", "5:50"), ("Crucifixed", "8:43"), ("Turtle Tilts", "17:08"), ("Always Be On That Lean", "23:51"), ("The Jo Chen Counter", "31:08"), ("Runaway (Feat Priit)", "34:50")],
    ],
    "shotgun-k-guard": [
        [("Intro", "0:00"), ("Basics - K Guard Overview", "0:35"), ("K Guard Principles", "4:40"), ("Knee Off The Mat", "11:50"), ("Scoop Grip", "16:32"), ("Grips", "19:59"), ("Secondary Leg / Reverse Scoop Grip", "24:29"), ("Backside / Frontside", "27:22"), ("Backside Top", "29:46"), ("Backside Bottom", "34:44"), ("Frontside Top", "40:05"), ("Frontside Bottom", "43:57"), ("Seated To K Lower Body", "49:00"), ("Seated To K Upper Body", "53:31"), ("Supine Guard To K Low Leg", "58:43"), ("Supine Guard To K Lasso", "1:02:12"), ("North-South To K", "1:04:01"), ("Reverse De La Riva To K", "1:05:43")],
        [("Backside - Backside Intro", "0:00"), ("Backside 50/50", "1:22"), ("Inside Heel Hook Backside", "3:30"), ("Inside Heel Hook Frontside", "11:56"), ("Inside Heel Hook Double 50/50", "16:46"), ("Following The Backstep", "21:05"), ("Reverse Aoki Outside", "27:16"), ("Reverse Aoki Inside", "32:53"), ("High Backstep", "36:33"), ("Matrix", "40:28"), ("X Hook Leg Drag", "44:05"), ("X Hook Backtake 1", "50:00"), ("X Hook Backtake 2", "54:31")],
        [("Frontside - Frontside Intro", "0:00"), ("Angle For Outside Leg Locks", "1:38"), ("Aoki Lock - Inside", "5:25"), ("Aoki Lock - Belly Down", "12:03"), ("Aoki Lock - Outside", "14:57"), ("Off-Balance Forward", "21:24"), ("Off-Balance Backward", "23:39"), ("Outside Heel Hook Inside", "27:04"), ("Outside Heel Hook Outside", "32:46"), ("Combining Subs Together", "37:37"), ("Leg Switch - Dilemma", "39:59"), ("Leg Switch - Sweep", "43:28"), ("Far Side K", "46:36"), ("Backroll Sweep", "49:04"), ("Saddle", "51:06")],
        [("Upperbody - Upperbody Introduction", "0:00"), ("Shotgun Armbar", "1:14"), ("Shotgun Armbar 2", "7:55"), ("Shotgun Armbar 3", "10:46"), ("Flower Sweep", "14:14"), ("Mirlock", "16:28"), ("Triangle Set Ups", "21:05"), ("Triangle Finish", "24:27"), ("Choibar", "28:09")],
    ],
}


def seconds(value):
    parts = [int(part) for part in value.split(":")]
    if len(parts) == 2:
        return parts[0] * 60 + parts[1]
    return parts[0] * 3600 + parts[1] * 60 + parts[2]


def chapters(course_id, volume):
    return [{"id": f"v{volume}-{index}", "title": title, "start_seconds": seconds(start), "official_start": start}
            for index, (title, start) in enumerate(OFFICIAL_CHAPTERS[course_id][volume - 1], 1)]
