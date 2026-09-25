# APPLIED 2026-09-19 — this sheet is spent.

> All 41 answers are in each app's `translations/ar/LC_MESSAGES/messages.po`
> and compiled. `ARABIC_TRANSLATION_QUESTIONS_REWARDS.md` is the decision
> trail. Kept only so the exact wording that was asked for is on record.

# Arabic — rewards card: fill-in sheet

**Write the Arabic after `AR:` on each line and send this back (or save it).**
Leave any line blank to keep it in English for now — nothing breaks either way.

Rules that matter:

- **Keep every placeholder exactly as written** — `%(days)s`, `{rate}`, `%%`.
  A dropped placeholder is a crash at render, and `test_placeholder_args.py`
  will catch it, but it is easier not to.
- **Don't worry about word order** — the layout flips to RTL on its own.
- If the **English** is ambiguous, say so instead of translating around it.
  Batch 1 changed an English string for exactly that reason.

---

### 1. `Manage Rewards Members`

AR: 

### 2. `That card number is already issued to another owner.`

AR: 

### 3. `Rewards card issued.`

AR: 

### 4. `Rewards card revoked.`

AR: 

### 5. `This bill carries a rewards-card discount. A staff discount can't be added on top of it, and can't replace it.`

AR: 

### 6. `That bill no longer exists.`

AR: 

### 7. `This bill doesn't carry a rewards-card discount.`

AR: 

### 8. `Rewards-card discount removed from this bill.`

AR: 

### 9. `Member discount must be a valid number.`

AR: 

### 10. `Member discount must be between 0%% and %(max)s%%.`
> Keep %(max)s and both %% exactly as written.

AR: 

### 11. `Member discount`
> **COLLISION RISK.** الخصم already = Discount (staff). Clean Up is deliberately الإعفاء عن الفئات القليلة, NOT الخصم. This is a THIRD discount concept and a cashier must tell them apart in a refusal message.

AR: 

### 12. `%(rate)s%% on eligible items`
> %(rate)s is the number, %% renders as %. Keep both placeholders.

AR: 

### 13. `Some items on this bill are not eligible and are charged in full.`

AR: 

### 14. `This stay carries a rewards-card discount, which this form cannot change.`

AR: 

### 15. `Clients Who Paid, Last %(months_back)s Months`
> CHANGED MEANING: was 'lifetime', now a trailing window. Keep %(months_back)s.

AR: 

### 16. `Avg. Spend / Client, Last %(months_back)s Months (%(currency_label)s)`
> CHANGED MEANING as above. Keep both placeholders.

AR: 

### 17. `Top Clients by Spend, Last %(months_back)s Months`
> CHANGED MEANING as above. Keep %(months_back)s.

AR: 

### 18. `Payments for visits, inpatient care and boarding, plus retail sales where a customer was identified at the till, less any refunds. Walk-in sales with no customer recorded aren't counted.`

AR: 

### 19. `Member`
> Short badge text, appears in a coloured pill next to a name.

AR: 

### 20. `Rewards Card`
> The programme's name — the clinic may already use a name with customers.

AR: 

### 21. `Expires in %(days)s days`
> Keep %(days)s exactly as written.

AR: 

### 22. `Card Number`

AR: 

### 23. `Member Since`

AR: 

### 24. `Expires`
> Label for a FUTURE date. Babel guessed منتهي الصلاحية ('expired') — wrong tense.

AR: 

### 25. `Never`
> Shown in the Expires field when a card has no expiry date.

AR: 

### 26. `Issued By`

AR: 

### 27. `The rewards programme is switched off in Settings.`

AR: 

### 28. `Revoke Card`

AR: 

### 29. `This card lapsed on %(date)s. Issuing a new one starts a fresh term.`
> Keep %(date)s exactly as written.

AR: 

### 30. `Not a member.`

AR: 

### 31. `Card Number (optional)`

AR: 

### 32. `Pre-filled from the term in Settings. Clear it for a card that never expires.`

AR: 

### 33. `Issue Card`

AR: 

### 34. `Customer (optional)`

AR: 

### 35. `Name, phone or card number`

AR: 

### 36. `Rewards card: {rate} off eligible items. A staff discount cannot be added on top.`
> JavaScript fills {rate} (it already includes the % sign). Keep {rate} in braces.

AR: 

### 37. `Could not search customers; check server connection.`

AR: 

### 38. `Member Discount (%%)`
> Settings field label. The %% renders as a single % sign.

AR: 

### 39. `0 switches the rewards programme off. Applies to eligible Price List items only.`

AR: 

### 40. `Card Valid For (Months)`

AR: 

### 41. `Pre-fills the expiry date when a card is issued. Existing cards keep the date they were given.`

AR: 
