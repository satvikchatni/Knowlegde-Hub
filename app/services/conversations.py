

def trim_history(messages,max_chars):
    kept,count=[],0
    for message in messages:
        size=len(message.content)
        if size+count>max_chars:
            break
        kept.append(message)
        count+=size
    kept.reverse() # restores chronological order, because we collected messages newest first
    while kept and kept[0].role!="user": #makes sure history starts with user message..., removes leading assistant message
        kept.pop(0)
    return kept
