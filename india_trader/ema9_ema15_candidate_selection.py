"""Read an existing V2 report and choose parameter candidates using TRAINING only.

The untouched chronological holdout is printed AFTER the selection.
Minimum sample prevents one-trade '100% win' configurations from winning.
"""
import argparse,json
from pathlib import Path

def choose(report,market,min_train=20):
    pool=[x for x in report["cases"] if x["market"]==market
          and x["parameters"]["entry_mode"]=="next_open"
          and x["parameters"]["slippage"]=="1.0"
          and x["parameters"]["trail_r"]=="1.0"
          and x["parameters"]["cutoff"]=="14:30:00"
          and x["parameters"]["stop_mode"]=="after_t1"
          and x["training"]["trades"]>=min_train]
    # Training-only ranking; no holdout data in score.
    pool.sort(key=lambda x:(x["training"]["profit_factor"] or 0,
                             x["training"]["net_inr"]),reverse=True)
    return pool

def main():
    p=argparse.ArgumentParser();p.add_argument("--report",required=True)
    p.add_argument("--out",required=True);a=p.parse_args()
    data=json.loads(Path(a.report).read_text())
    output={"selection":"TRAINING_ONLY_WITH_MIN_20_TRAINING_TRADES",
            "warning":"Holdout examined only after candidate ranking; retrospective analysis still exploratory.",
            "markets":{}}
    for market in ("NIFTY","SENSEX"):
        ranked=choose(data,market)
        output["markets"][market]=[{"parameters":r["parameters"],
          "training":r["training"],"holdout":r["holdout"],"all":r["all"]} for r in ranked]
        print(market,"eligible",len(ranked),flush=True)
        for r in ranked[:5]:
            print(r["parameters"]["angle"],r["parameters"]["body_min"],
                  "train",r["training"]["net_inr"],r["training"]["trades"],
                  "holdout",r["holdout"]["net_inr"],r["holdout"]["trades"],flush=True)
    out=Path(a.out);out.parent.mkdir(parents=True,exist_ok=True)
    out.write_text(json.dumps(output,indent=2)+"\n")
if __name__=="__main__":main()
