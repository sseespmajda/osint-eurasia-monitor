import database
import json
import pandas as pd

def analyze_channels():
    events = database.get_all_events()
    if not events:
        print("No events found in database.")
        return

    # Channel stats: {channel_name: {"original": 0, "duplicate": 0, "merged": 0}}
    stats = {}

    for e in events:
        ch = e['source_channel']
        if ch not in stats:
            stats[ch] = {"original": 0, "duplicate": 0, "merged": 0}
        
        # Check if it's a primary entry or a child update
        if e['parent_id'] is None:
            stats[ch]["original"] += 1
        else:
            stats[ch]["duplicate"] += 1
            
        # Check the 'sources' JSON for merged mentions (exact hash matches)
        try:
            sources = json.loads(e['sources'])
            for s in sources:
                if s != ch:
                    if s not in stats:
                        stats[s] = {"original": 0, "duplicate": 0, "merged": 0}
                    stats[s]["merged"] += 1
        except:
            pass

    # Calculate percentages
    data = []
    for ch, counts in stats.items():
        total = counts['original'] + counts['duplicate'] + counts['merged']
        dup_total = counts['duplicate'] + counts['merged']
        dup_rate = (dup_total / total * 100) if total > 0 else 0
        
        data.append({
            "Channel": ch,
            "Total Contributions": total,
            "Original Posts": counts['original'],
            "Duplicates/Updates": counts['duplicate'],
            "Exact Hash Matches": counts['merged'],
            "Duplication Rate (%)": round(dup_rate, 1)
        })

    df = pd.DataFrame(data).sort_values("Duplication Rate (%)", ascending=False)
    
    print("\n--- CHANNEL DUPLICATION ANALYSIS ---")
    print(df.to_string(index=False))
    
    high_dups = df[df['Duplication Rate (%)'] > 70]
    if not high_dups.empty:
        print("\n[RECOMMENDATION] Consider removing these high-duplication channels (>70%):")
        for _, row in high_dups.iterrows():
            print(f"- {row['Channel']} ({row['Duplication Rate (%)']}% duplicate)")

if __name__ == "__main__":
    analyze_channels()
