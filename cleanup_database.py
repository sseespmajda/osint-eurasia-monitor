import database
import json

def cleanup():
    events = database.get_all_events()
    to_delete = []
    
    # Keywords for ad-weeding in old data
    ad_keywords = [
        '#реклама', 'подписывайтесь', 'vpn', 'crypto', 'trading', 'бонусы',
        'зарабатывать', 'курсы', 'скидка', 'промокод', 'реферальная',
        'подписка', 'бесплатно', 'инвестиции', 'сигналы', 'обучение',
        'p2p', 'арбитраж', 'казино', 'casino', 'ставка', 'выплаты'
    ]

    print(f"Analyzing {len(events)} events for cleanup...")

    for e in events:
        # 1. Target Sports & Culture
        # We check both the original event_type and the summary text for keywords
        etype = (e.get('event_type') or "").lower()
        summary = (e.get('text_summary') or "").lower()
        raw = (e.get('raw_message') or "").lower()
        
        is_trash = False
        
        # Sector match
        if any(k in etype for k in ['sport', 'culture', 'society']):
            is_trash = True
            
        # Specific keywords for sports/culture if they were mislabeled
        if any(k in summary for k in ['skier', 'medal', 'olympic', 'paralympic', 'gold medal', 'passed away at age']):
            is_trash = True
            
        # 2. Target Ads
        if any(k in raw for k in ad_keywords):
            is_trash = True
            
        if is_trash:
            to_delete.append(e)

    if not to_delete:
        print("No matches found for cleanup.")
        return

    print(f"Deleting {len(to_delete)} unrelated events...")
    for entry in to_delete:
        print(f" - Removing: {entry['country']} | {entry['text_summary'][:50]}...")
        database.delete_event(entry['id'])

    print("\nCleanup complete. Database is now focused on core intelligence.")

if __name__ == "__main__":
    cleanup()
