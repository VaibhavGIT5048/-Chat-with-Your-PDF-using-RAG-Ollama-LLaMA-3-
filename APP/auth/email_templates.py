"""HTML/plaintext bodies for transactional email.

Kept separate from APP/email.py so the delivery mechanics (ACS client, retry,
env wiring) stay readable next to a ~180-line table-based HTML layout.

Table-based layout with inline styles on purpose — email clients (Outlook
especially) don't support flex/grid, external stylesheets, or most modern CSS.
The <style> block only carries the dark-mode overrides and mobile media query,
which clients that ignore <style> simply fall back from gracefully.
"""

from __future__ import annotations

import os

# Where "OPEN GROUNDED-RAG" points. Env-overridable so staging/local builds can
# aim the button at their own frontend instead of the production Pages site.
APP_PUBLIC_URL = os.getenv("APP_PUBLIC_URL", "https://vaibhavgit5048.github.io/private-rag-core/")

# Institution details shown in the footer.
ORG_URL = "https://manavrachna.edu.in/mriirs"
ORG_SHORT = "MRIIRS"
ORG_ADDRESS = (
    "Manav Rachna International Institute Of Research And Studies, Plot A, "
    "Manav Rachna Campus Rd, Gadakhor Basti Village, Sector 43, "
    "Faridabad, Haryana 121004"
)

OTP_SUBJECT = "Your verification code"


def otp_plaintext(code: str, expiry_minutes: int = 10) -> str:
    """Plaintext alternative. Not optional — a message with only an HTML part
    scores worse with spam filters, and some clients render text-only.
    """
    return (
        f"Your Grounded-RAG verification code is {code}\n\n"
        f"Enter this code to finish signing in. It expires in {expiry_minutes} minutes.\n\n"
        f"Didn't request this? You can safely ignore this email - no account "
        f"changes will be made without this code.\n\n"
        f"{ORG_SHORT} - {ORG_URL}\n"
        f"{ORG_ADDRESS}\n"
    )


def otp_html(code: str, expiry_minutes: int = 10) -> str:
    return f"""<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta http-equiv="X-UA-Compatible" content="IE=edge">
<meta name="color-scheme" content="light dark">
<meta name="supported-color-schemes" content="light dark">
<title>{OTP_SUBJECT}</title>
<!--[if mso]>
<noscript>
<xml><o:OfficeDocumentSettings><o:PixelsPerInch>96</o:PixelsPerInch></o:OfficeDocumentSettings></xml>
</noscript>
<![endif]-->
<style>
  body, table, td {{ -ms-text-size-adjust: 100%; -webkit-text-size-adjust: 100%; }}
  table, td {{ mso-table-lspace: 0pt; mso-table-rspace: 0pt; }}
  img {{ border: 0; line-height: 100%; outline: none; text-decoration: none; }}
  body {{ margin: 0; padding: 0; width: 100% !important; background-color: #f3f2f2; }}
  a {{ text-decoration: none; }}
  @media (prefers-color-scheme: dark) {{
    .bg-outer {{ background-color: #17100e !important; }}
    .bg-card {{ background-color: #201e1d !important; border-color: #4d170e !important; }}
    .txt-main {{ color: #f8f4f4 !important; }}
    .txt-mute {{ color: #bab6b6 !important; }}
    .bg-code {{ background-color: #2d2b2b !important; border-color: #ec3013 !important; }}
    .txt-code {{ color: #ff9783 !important; }}
    .hr-line {{ border-color: #444141 !important; }}
  }}
  @media screen and (max-width: 600px) {{
    .container {{ width: 100% !important; }}
    .px {{ padding-left: 20px !important; padding-right: 20px !important; }}
    .code-digits {{ font-size: 40px !important; letter-spacing: 10px !important; }}
  }}
</style>
</head>
<body style="margin:0; padding:0; background-color:#f3f2f2;">
  <span style="display:none; visibility:hidden; opacity:0; color:transparent; height:0; width:0; overflow:hidden; mso-hide:all; font-size:1px; line-height:1px;">
    Your Grounded&#8209;RAG verification code is inside &mdash; it expires in {expiry_minutes} minutes.
  </span>

  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" class="bg-outer" style="background-color:#f3f2f2;">
    <tr>
      <td align="center" style="padding: 48px 16px;">

        <table role="presentation" width="600" cellpadding="0" cellspacing="0" border="0" class="container" style="width:600px; max-width:600px;">

          <!-- Logo header -->
          <tr>
            <td align="left" style="padding: 0 0 32px 0;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="10" style="background-color:#ec3013; font-size:0; line-height:0;">&nbsp;</td>
                  <td style="padding-left:12px; font-family: Arial, Helvetica, sans-serif; font-size:20px; font-weight:800; letter-spacing:-0.3px; color:#201e1d;" class="txt-main">
                    GROUNDED&#8209;RAG
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Card -->
          <tr>
            <td class="bg-card px" style="background-color:#f8f4f4; border:2px solid #201e1d; padding: 48px 48px;">

              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td style="font-family: Arial, Helvetica, sans-serif; font-size:12px; font-weight:800; letter-spacing:2.5px; text-transform:uppercase; color:#ec3013; padding-bottom:16px;">
                    Verify it&rsquo;s you
                  </td>
                </tr>
                <tr>
                  <td style="font-family: Arial, Helvetica, sans-serif; font-size:28px; line-height:1.25; font-weight:800; letter-spacing:-0.5px; color:#201e1d;" class="txt-main">
                    Welcome to Grounded&#8209;RAG.
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:14px; font-family: Arial, Helvetica, sans-serif; font-size:16px; line-height:1.6; color:#605d5d;" class="txt-mute">
                    Enter this code to finish signing in. It confirms the request came from you, and only you.
                  </td>
                </tr>

                <!-- divider -->
                <tr>
                  <td style="padding: 32px 0;">
                    <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                      <tr><td height="2" class="hr-line" style="background-color:#201e1d; font-size:0; line-height:0;">&nbsp;</td></tr>
                    </table>
                  </td>
                </tr>

                <!-- code box -->
                <tr>
                  <td align="center">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="100%">
                      <tr>
                        <td align="center" class="bg-code" style="background-color:#201e1d; border:2px solid #ec3013; padding: 28px 24px;">
                          <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                            <tr>
                              <td style="font-family: Arial, Helvetica, sans-serif; font-size:11px; font-weight:700; letter-spacing:2px; text-transform:uppercase; color:#ff9783; padding-bottom:10px;" align="center">
                                Your code
                              </td>
                            </tr>
                            <tr>
                              <td class="code-digits txt-code" align="center" style="font-family: 'Courier New', Courier, monospace; font-size:48px; font-weight:700; letter-spacing:14px; color:#ffffff; padding-left:14px;">
                                {code}
                              </td>
                            </tr>
                          </table>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td align="center" style="padding-top:18px; font-family: Arial, Helvetica, sans-serif; font-size:13px; color:#7d7979;" class="txt-mute">
                    This code expires in <strong style="color:#201e1d;" class="txt-main">{expiry_minutes} minutes</strong>.
                  </td>
                </tr>

                <!-- CTA button -->
                <tr>
                  <td align="left" style="padding-top:32px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                      <tr>
                        <td bgcolor="#ec3013" style="background-color:#ec3013;">
                          <a href="{APP_PUBLIC_URL}" target="_blank" style="display:block; padding:16px 32px; font-family: Arial, Helvetica, sans-serif; font-size:15px; font-weight:800; letter-spacing:0.4px; color:#ffffff;">
                            OPEN GROUNDED&#8209;RAG&nbsp;&rarr;
                          </a>
                        </td>
                      </tr>
                    </table>
                  </td>
                </tr>

                <tr>
                  <td style="padding-top:28px; font-family: Arial, Helvetica, sans-serif; font-size:13px; line-height:1.6; color:#7d7979;" class="txt-mute">
                    Didn&rsquo;t request this? You can safely ignore this email &mdash; no account changes will be made without this code.
                  </td>
                </tr>
              </table>

            </td>
          </tr>

          <!-- spacer -->
          <tr><td style="font-size:0; line-height:0; height:40px;">&nbsp;</td></tr>

          <!-- footer -->
          <tr>
            <td class="px" style="padding: 0 4px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr><td height="2" style="background-color:#d7d3d3; font-size:0; line-height:0;">&nbsp;</td></tr>
              </table>
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin-top:20px;">
                <tr>
                  <td style="font-family: Arial, Helvetica, sans-serif; font-size:12px; line-height:1.7; color:#9b9797;">
                    Grounded&#8209;RAG &middot; Cloud&#8209;hosted retrieval over your own documents<br>
                    Sent to you because a sign&#8209;in was requested for your account.
                  </td>
                </tr>
                <!-- Rendered as plain text, not links, until real URLs exist.
                     example.com is IANA's reserved documentation domain and
                     linking to it is a recognised spam heuristic — on a
                     zero-reputation azurecomm.net sender that's a cost we
                     can't afford. Restore the <a href> wrappers once these
                     point somewhere real. -->
                <tr>
                  <td style="padding-top:14px; font-family: Arial, Helvetica, sans-serif; font-size:12px; line-height:1.7; color:#9b9797;">
                    Help Center &nbsp;&middot;&nbsp; Support &nbsp;&middot;&nbsp; Manage preferences
                  </td>
                </tr>
                <tr>
                  <td style="padding-top:14px; font-family: Arial, Helvetica, sans-serif; font-size:11px; line-height:1.6; color:#bab6b6;">
                    <a href="{ORG_URL}" target="_blank" style="color:#bab6b6; text-decoration:underline;">{ORG_SHORT}</a>
                    &middot; {ORG_ADDRESS}
                  </td>
                </tr>
              </table>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>
"""
