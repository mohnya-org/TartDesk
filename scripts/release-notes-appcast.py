"""Embed the draft GitHub Release body before publishing the appcast asset."""
import json
from pathlib import Path
import sys
import xml.etree.ElementTree as ET

SPARKLE = 'http://www.andymatuschak.org/xml-namespaces/sparkle'
ET.register_namespace('sparkle', SPARKLE)
ET.register_namespace('dc', 'http://purl.org/dc/elements/1.1/')


def embed(appcast, release_json):
    release = json.loads(Path(release_json).read_text())
    notes = release['body']
    if notes is not None and not isinstance(notes, str):
        raise ValueError('Release body must be text or null')
    url = release['url']
    if not isinstance(url, str) or not url.startswith('https://github.com/'):
        raise ValueError('Expected a GitHub release URL')
    tree = ET.parse(appcast)
    items = tree.findall('./channel/item')
    if len(items) != 1:
        raise ValueError('Expected exactly one update')
    item = items[0]
    enclosure = item.find('enclosure')
    if enclosure is None or not enclosure.get(f'{{{SPARKLE}}}edSignature'):
        raise ValueError('Expected a signed update enclosure')
    for name in ('description', f'{{{SPARKLE}}}releaseNotesLink', f'{{{SPARKLE}}}fullReleaseNotesLink'):
        for old in item.findall(name):
            item.remove(old)
    # These apps ship Sparkle 2.10 on macOS 14+. Preserve the Release Markdown.
    description = ET.SubElement(item, 'description', {f'{{{SPARKLE}}}format': 'markdown'})
    description.text = notes or 'No release notes were provided for this release.'
    ET.SubElement(item, f'{{{SPARKLE}}}fullReleaseNotesLink').text = url
    # Only feed metadata changes; enclosure URL, length, versions and EdDSA
    # signature remain untouched. These feeds do not enable SURequireSignedFeed.
    tree.write(appcast, encoding='utf-8', xml_declaration=True)


if __name__ == '__main__':
    embed(*sys.argv[1:])
