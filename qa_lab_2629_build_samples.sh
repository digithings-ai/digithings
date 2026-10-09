#!/bin/bash
set -u
export PATH="/opt/homebrew/bin:$HOME/.local/bin:$PATH"
SC="/private/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/paperclip-run-dig-2629-0f4dd87d-d07-IBYmNS"
OUT="$SC/wav"; mkdir -p "$OUT"
echo "CONTROL say=$(command -v say) sox=$(command -v sox)"

mk() {
  name="$1"; voice="$2"; text="$3"
  aiff="$OUT/$name.aiff"; wav="$OUT/$name.wav"
  /usr/bin/say -v "$voice" -r 170 -o "$aiff" "$text" 2>&1 || { echo "SAY-FAIL $name"; return 1; }
  [ -s "$aiff" ] || { echo "SAY-EMPTY $name"; return 1; }
  /opt/homebrew/bin/sox "$aiff" -r 16000 -c 1 -b 16 -t wav "$wav" 2>&1 || { echo "SOX-FAIL $name"; return 1; }
  [ -s "$wav" ] || { echo "SOX-EMPTY $name"; return 1; }
  return 0
}

mk s1_default          Samantha "The quick brown fox jumps over the lazy dog." || exit 1
mk s2_numbers          Samantha "Ship number forty two, on March third, twenty twenty six." || exit 1
mk s3_dictation_shape  Samantha "Please add the meeting notes to the sprint board before Friday." || exit 1

n=$(ls -1 "$OUT"/*.wav 2>/dev/null | wc -l | tr -d ' ')
echo "wav count = $n"
if [ "$n" != "3" ]; then echo "ABORT: expected 3 wavs, got $n"; exit 1; fi

for f in "$OUT"/*.wav; do
  printf '%s\t%s\t%s\t%s\n' "$(basename "$f" .wav)" "$(shasum -a 256 "$f" | cut -d' ' -f1)" "$(wc -c < "$f" | tr -d ' ')" "$(/opt/homebrew/bin/sox --i -D "$f" 2>/dev/null | head -1)"
done | sort > "$SC/lab/samples.tsv"
echo "--- sample set (name sha256 bytes duration_s) ---"; cat "$SC/lab/samples.tsv"
echo "--- SAMPLE-SET HASH ---"
shasum -a 256 "$SC/lab/samples.tsv" | cut -d' ' -f1 | tee "$SC/lab/sample-set.sha256"
