"""生成演示数据：真实 B 站视频元信息 + 封面，配一份手写样例文案。

用途：在没有 LLM key / 没有 whisper 模型时，也能完整跑通「清洗 -> 摘要 -> 改写 -> 排版」，
让人先看到 V1 的杂志长什么样。所有样例文案在界面上都标记为「演示」。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, source  # noqa: E402

SEEDS = [
    {
        "bvid": "BV1yUHP6rEYD",
        "transcript": """大家好，今天我们来聊一个特别实际的问题：你需要多少钱，才能不用上班。
先给结论，很多人以为是几千万，其实按经典算法，大概是你一年开销的二十五倍。
这个算法来自一九九四年那篇很有名的研究，他们回测了美国几十年的市场数据，发现如果你每年只取走资产的百分之四，
在绝大多数三十年窗口里，这笔钱都不会被花光。所以年开销乘以二十五，就是你的目标数字。
但我要提醒一句，百分之四不是物理定律，它更像一个恒温器。它假设你拿到的是平均收益，
它没有告诉你，如果你刚好在退休第一年遇到大跌，会发生什么。顺序风险这个东西，比平均收益重要得多。
还有一个反直觉的点：你每砍掉一万块年开销，目标就直接少二十五万。所以省钱比赚钱效率高得多。
那问题就变成：你愿意为自由承担多少不确定性。""",
        "summary": "财富自由的常见算法是把年开销乘以二十五，对应每年提取资产百分之四的历史回测结论。"
        "作者强调这不是定律而是恒温器式的近似：它依赖平均收益假设，无法覆盖退休初期遭遇大跌的顺序风险。"
        "更反直觉的一点是，每减少一万元年开销，所需本金就少二十五万，因此压缩开支的效率远高于提高收益。"
        "结论由此从「攒多少钱」转向「能为自由承受多大不确定性」。",
        "title": "Freedom Has a Price Tag, and It Fits in One Number",
        "body": """Ask ten people how much money would let them stop working, and you will collect ten confident, incompatible answers. Run the question through a century of market data instead, and the answers collapse into something almost embarrassingly simple: roughly twenty-five times your yearly spending.

The arithmetic traces back to a 1994 study of American portfolios, which found that withdrawing about four percent of a balanced fund each year survived nearly every thirty-year window on record. Multiply your annual costs by twenty-five and you have a target. Spend less, and the target shrinks faster than most people expect—every thousand dollars trimmed from a year of living removes twenty-five thousand from the sum you need.

It is tempting to read four percent as a law of nature. It behaves more like a thermostat: it assumes average returns, tolerates mediocre decades, and says nothing about the particular year you retire into. A market that falls early bites deeper than one that falls late, even when the final average is identical.

So the honest question is not how much freedom costs, but how much uncertainty you can carry while paying for it.""",
    },
    {
        "bvid": "BV1tjHA6yEnG",
        "transcript": """你猜日本人现在在卖什么？虾壳。就是我们吃虾剥下来扔掉的那层壳。
其实不是新鲜事，甲壳素这个东西在工业上用了很多年，只是这两年因为处理成本上涨，
加上供应链想找不跟耕地抢资源的原料，虾壳突然就从垃圾变成了原料。
它的核心成分叫几丁质，跟昆虫外骨骼是同一类东西，很硬。加工成壳聚糖之后能干很多事：
增稠、做可食用保鲜膜、给酒澄清、在水处理里吸附重金属。
所以你看，一个东西是不是废物，其实取决于你有没有找到第二个用途。
对渔业公司来说，以前虾壳是要花钱运走的，现在是可以卖钱的，这一进一出，利润结构就变了。""",
        "summary": "日本市场上的虾壳从需要付费处理的废料变成可出售的原料，核心成分是几丁质，与昆虫外骨骼同类。"
        "加工成壳聚糖后可用于增稠、制作可食用保鲜膜、澄清酒类以及在水处理中吸附重金属。"
        "推动这一转变的是处理成本上涨，以及供应链希望获得不与耕地争夺资源的原料。"
        "同一批渔获由此被卖出两次，废料流变成第二份收成，渔业的利润结构随之改变。",
        "title": "The Shell You Throw Away Is Someone Else's Ingredient",
        "body": """In a Japanese supermarket, the parts of dinner that most kitchens discard have started appearing with prices attached. Shrimp shells, long treated as the unglamorous residue of a seafood industry, are being sold—ground, extracted, and reformulated into something closer to a raw material than a waste product.

The useful molecule is chitin, the fibrous substance that gives shells and insect exoskeletons their toughness. Processed into chitosan, it becomes a versatile agent: it can thicken sauces, form edible films that keep fish fresh, clarify wine, and bind heavy metals in water treatment. None of that is new chemistry. What is new is the economics. As disposal costs climb and supply chains hunt for material that does not compete with farmland, a waste stream starts to look like a second harvest.

The shift is easiest to see as a reversal of perspective. A shell is not a smaller shrimp; it is a different product that happens to arrive attached to one. Industries that learn to sell both ends of the same catch can extract margin from what they once paid to haul away.""",
    },
    {
        "bvid": "BV1sPHP6kE82",
        "transcript": """今天讲特斯拉。先说他最出名的那个传说：他发明了能分裂地球的机器。
一九零三年确实有报纸这么写，但那是报纸写的，不是他证明的。
他真正厉害的东西，是交流电感应电机，一八八几年演示的，直接让远距离输电变得可行，
也基本决定了当年那场电流之战的结局。这个是实打实的工程成就。
后来那些神话，什么免费能源、死光、被财团打压的天才，每一条都有点影子，但都被放大了。
我觉得大家喜欢特斯拉，是因为他太适合当一个镜子了：我们都愿意相信，
世界会辜负最聪明的人。可真实的他，是个天才工程师，同时也是个很差的商人，
最后死在纽约的旅馆里，一个人，喂鸽子。
他造出来的机器现在还在转，他没造出来的那些，才是我们记得的。""",
        "summary": "特斯拉的「分裂地球」传说源自一九零三年的报纸报道，并非他本人证明的成果。"
        "他真正的工程成就是交流电感应电机，使远距离输电变得可行，并影响了电流之战的结局。"
        "免费能源、死光、被财团打压等神话各有影子但都被放大；公众青睐这一形象，是因为它映照了"
        "「世界会辜负最聪明的人」这一心理预期。真实的他是天才工程师同时也是糟糕的商人，"
        "晚年独居纽约旅馆，而真正造出的机器仍在运转。",
        "title": "Tesla Promised to Split the Earth. He Never Did.",
        "body": """During the summer of 1903, newspapers reported that Nikola Tesla had invented a device capable of splitting the planet "like an apple." He had not. What he had was a laboratory in Colorado Springs, an enormous ambition, and a press corps that found ambition easier to print than physics.

The real Tesla was formidable in a quieter register. His alternating-current induction motor, demonstrated in the 1880s, made long-distance electricity practical and helped settle the current wars in favor of AC. The myths arrived later: free energy, death rays, a genius betrayed by rivals and forgotten by history. Each contains a grain of truth and a great deal of embellishment.

Part of the appeal is that Tesla makes an unusually clean mirror. We want the story of a man too brilliant for his own era, because it flatters our suspicion that the world undervalues its best minds. The historical record is messier: a gifted engineer, a poor businessman, a man who died alone in a New York hotel room, feeding pigeons.

The machines he actually built still run. The ones he merely promised are the ones we remember.""",
    },
]


def main() -> None:
    client = source.BiliClient(cookie="")
    seed_out, cache = [], {}
    for s in SEEDS:
        bvid = s["bvid"]
        try:
            info = client.video_info(bvid)
        except Exception as exc:
            print(f"!! {bvid} 取信息失败：{exc}")
            continue
        cover = config.MEDIA_DIR / bvid / "cover.jpg"
        got = client.download_cover(info.get("cover", ""), cover)
        print(f"   {bvid} {info['title'][:30]} cover={'ok' if got else 'missing'}")
        seed_out.append(
            {
                "bvid": bvid,
                "title": info["title"],
                "author": info["author"],
                "pubdate": info.get("pubdate"),
                "cover": str(cover) if got else "",
                "transcript": s["transcript"],
            }
        )
        cache[bvid] = {"summary": s["summary"], "title": s["title"], "body": s["body"]}

    cache["__issue__"] = {
        "headline": "What We Keep, What We Throw Away, What We Invent",
        "lede": "Three stories about money, waste and myth — compressed, translated and rebuilt for a reader with ten minutes.",
    }
    (config.DEMO_DIR / "seed.json").write_text(json.dumps(seed_out, ensure_ascii=False, indent=2), encoding="utf-8")
    (config.DEMO_DIR / "llm_cache.json").write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n写入 {len(seed_out)} 条演示数据 -> {config.DEMO_DIR}")


if __name__ == "__main__":
    main()
