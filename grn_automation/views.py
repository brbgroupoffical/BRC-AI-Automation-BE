from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation, AutomationStep
from .serializers import AutomationUploadSerializer, GRNAutomationSerializer
from rest_framework.generics import RetrieveAPIView, ListAPIView
from .utils.extraction import AWSTextractSAPExtractor
from .utils.vendor import get_vendor_code_from_api
from .utils.grns import fetch_grns_for_vendor, filter_grn_response
from .utils.matcher import matching_grns
from .utils.invoice import create_invoice
from .utils.validation import validate_invoice_with_grn 
# from .tasks import run_full_automation
import logging
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation
from .serializers import GRNAutomationSerializer
from .pagination import TenResultsSetPagination
from django.utils import timezone


logger = logging.getLogger(__name__)


class UserAutomationDetailView(RetrieveAPIView):
    """
    Retrieve details of a single automation job for the logged-in user.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        # Ensure user can only see their own jobs
        return GRNAutomation.objects.filter(user=self.request.user)


class UserAutomationListView(ListAPIView):
    """
    List all automation jobs for the logged-in user with pagination (10 per page).
    Always sorted by `created_at` in descending order.
    """
    serializer_class = GRNAutomationSerializer
    permission_classes = [IsAuthenticated]
    pagination_class = TenResultsSetPagination

    def get_queryset(self):
        return (
            GRNAutomation.objects
            .filter(user=self.request.user)
            .order_by("-created_at")  
        )


class BaseAutomationUploadView(APIView):
    permission_classes = [IsAuthenticated]
    case_type = GRNAutomation.CaseType.ONE_TO_ONE

    def post(self, request, *args, **kwargs):
        if isinstance(request.data, dict):
            data = request.data  # If it's already a dict, just use it
        else:
            data = request.data.dict()  # Otherwise, safely call .dict() on it


        serializer = AutomationUploadSerializer(data=data, context={"request": request})
        if serializer.is_valid():
            automation = serializer.save()
            automation.file.close()

            # always fetch single step row
            step = automation.steps.first()

            # mark automation as running
            automation.status = GRNAutomation.Status.RUNNING
            automation.save(update_fields=["status"])

            # file_path = automation.file.path
            # extractor = AWSTextractSAPExtractor()
            # response = extractor.extract_sap_data(file_path)

            # result_status = response["status"]
            # message = response["message"]
            # result = response["data"]

            result_status = "success"
            message = "Extracted successfully."
            # result = {
            #     "sap_fields": {
            #         # "vendor_code": 'S00274',
            #         "vendor_code": "S00274",
            #         "po_number": 9,
            #         "vendor_name": "JOTUN POWDER COATINGS S.A. CO. LTD"
            #     }
            # }
            result = {
  "document_analysis": {
    "key_value_pairs": {
      "Date :": "31/08/25",
      "Description": "PVC GRANULES GREEN 6005) (1250KGS/JUMBO BAG) (NO OF BAGS 40)",
      "Ref. :": "16065",
      "Discount %": "0.00",
      "Item No.": "CMGR0001",
      "Total Excluding Tax": "SAR 240,000.00",
      "Remarks:": "Based on Purchase Request 971. Based on Purchase Orders 3125.",
      "Total": "SAR 240,000.00",
      "Goods Receipt PO :": "16065",
      "Branch :": "Fence Factory",
      "Supplier Ref. No. :": "INV-129/25",
      "For Customer Use": "Above goods received in good order and condition",
      "Qty (Stock UoM)": "50,000",
      "Price": "SAR 4,800.00",
      "Qty": "50",
      "Vendor ID :": "S01609",
      "#": "1",
      "Fax :": "300188758500003",
      "Credit Term :": "90days",
      "Page No.": "1",
      "JEDDAH": "SAUDI ARABIA",
      "Pratestion": "leruss",
      "Website": "www.plastopacks.com",
      "P.O. Box:": "23599,",
      "E-mail:": "info@plastopacks.com",
      "Fax:": "+974 44503723",
      "PAYMENT TERMS:": "CAD 90 DAYS FEOM THE DATE OF TRUCK CONSIGNMENT NOTE",
      "Tel:": "+974 44934181",
      "Certificate No.": "18804-Q15-001",
      "angell sol p\u00e4g p3, Wi,Lind": "2436/25",
      "39042200": "gmiall plail is,",
      "(s)grew Jus)": "240,000.00",
      "algiv ub p3)": "3125",
      "C.R. No.": "60446,",
      "(jb)": "50.00",
      "Street No.:": "12",
      "pj": "129/25",
      "\u00f6l-gll": "ib",
      "its clip": ": clicall put clill Juples",
      "\u00f6lagli you Juj)": "4,800.00",
      "p\u00e5)": "129/25",
      "(BRWAQAQA) Eight": "(10000-1775-933)",
      "New": "Industrial Area, Doha, State of Qatar",
      "QA48BRWA 0000 0000 0100 00177 5933 :": "IBAN p\u00e4g gl labri just oilg 510 Eli sill sigall",
      "40 :": "see",
      ":Ugait": "+974 44503723/ +97444503670",
      "igat": "00966-539201154 :",
      "\u00e4ills his usgls 39.": "1",
      "Code": "PVC GR 1008",
      "Number": "4535/25",
      "Item": "1",
      "Website:": "www.plastopacks.com",
      "P. O Box :": "5489",
      "Date": "26.08.2025",
      "Delivered Through:": "ALHAMAMI, ABDULLAH SALEM A & USMAN",
      "HS CODE :": "39042200",
      "TEL :": "6355666",
      "so NO :": "2436/25",
      "FAX :": "6375474",
      "PREPARED BY: (STORES)": "QueM",
      "CHECKED BY: (SALES)": "CHECKED BY: (ACCOUNTS)",
      "Our Refer.": "EXP PL 129/25",
      "Unit": "MT",
      "Quantity": "50",
      "Received the material in good condition": "yru by isui cris",
      "ID NO:": "1113929200 & 2327913758",
      "White (Customer) Yellow": "30-08-25",
      "Project Details": "SUPPLY OF PVC COMPOUND",
      "MOBILE NO :": "55967420 & 33252803",
      "NATIONALITY": "SAUDI & SAUDI",
      "One": "Qty. as above",
      "VEHICLE NO:": "4596 & 5015",
      "Building No.": "8,",
      "REPORTED WITHIN 48": "HRS (FOURTY EIGHT HRS) OF DELIVERY IN WRITING TO NO COMPLAINT WILL BE DEALT BEYOND THIS PERIOD FOR QUANTITY OR QUALITY OF MATERIALS SUPPLIED AS ABOVE.",
      "3hall ujgll (jb)": "50.00",
      "aNgell sol p3) p3) Will": "2436/25",
      "\u00f6lall": "jb",
      "{cytill": "23.08.2025",
      "p\u00e4g": "129/25",
      "algin ub p3)": "3125",
      "39042200 :": "guiall plail jos",
      "se (BAGS)": "40",
      "\u0440\u0451,": "1",
      "on are 3 gliani liatiml": "An",
      "igats": "00966-539201154 :",
      "129/25 :": "\u00f6jg\u00fclill pg",
      "Terms the": "last",
      "lec is ', giall JJC": "Jb I us 40.000",
      "(is juist ) juisll pubill js, HS Code": "39042200",
      ":Simall (ii) (whist)": "OK",
      "pilall": "ib 50.800",
      "glull is,": "in. Juin this sales",
      "sincell": "ib 50.000",
      "www.qatarchamber.com": "iii, jistyl will jub is is whall wildfall in Lail,",
      ":ail gic I giiall pul": "issull jbs slis and 09 jo LS jists J4 givels ,Las is Nill dyclinall d\u00e9bialltatis giftely We swall is inall",
      "injell calill Jgl": "who Jgyl iiib all citainall",
      "in greall shall --": "st,VI i jall retail",
      "illiable": ":0 gilall (u)li, ag, 129/25 23-08-2025",
      "in": "2025-15230",
      "QATAR CHAMBER": "thi",
      "in greall dyalinall 5 1's": "00966539201154",
      "2,1,11 all achieve Livis": "do is jell just",
      "inill Jas sli, and": "1 sjisia s. SLL, inc)",
      ":": "Geoul p\u00e4ll",
      "25/08/2025": ":?",
      "WEIGHTBRIDGE TICKET PRINT": "PGC",
      "Product": "PVC",
      "Transporter": "SUPPI jer",
      "Tel.:": "6355666",
      "Invoice No.": "36615",
      "2nd Weight": "14790 Kg",
      "COSEC. NO.": "73241",
      "DATE": "30/08/2025 08:27 AM 30/08/2025 11.14.AM",
      "NET Weight": "25420 Kg",
      "P.O. Box :": "5489 Jeddah 21422",
      "BRC": "10/ 1",
      "5015ERA": "40420 Kg 15000",
      "Operator :": "OAO",
      "Transporter:": "GRANULES SUPPLIER",
      "Product:": "PVC",
      "Customer :": "PLASTO PACK FACTORY",
      "Grierr": "0819 : 0.00",
      "AFA": "Inc.",
      "Tel. Jeddah-3 Fence:": "(012) 6358 145/ 6358 146 / 6358 147",
      "Tel. Dammam:": "(013) 8082954",
      "UoM": "Ton",
      "Item Code": "CMGR0001",
      "VAT": "0.00 1",
      "TOTAL": "240,000.00",
      "Payment Term:": "90days",
      "Com. Reg.": "4030008649",
      "Fax Dammam:": "(013) 8124103",
      "Delivery Date": "31-August-2025",
      "Supplier Address:": "\"PLOT #8, 12th STREET, NEW INDUSTRIAL AREA, DOHA QATAR\"",
      "U.PRICE": "4,800.00",
      "VAT Reg.": "No: 300188758500003",
      "QTY": "50.00",
      "Deliver To:": "658th Street Near Left @ 4th Round About JEDDAH SAUDI ARABIA",
      "Page": "1 of 1",
      "DESCRIPTION OF GOODS": "PVC GRANULES GREEN",
      "Line Total": "240,000.00",
      "Fax Jeddah": "(012)6375474",
      "Supplier:": "S01609",
      "Tel. Riyadh:": "(011) 4602692 4602703",
      "Tel. Jeddah": "(012) 6355666 / 6364724 / 6379507 / 6375285",
      "SAR": "Two Hundred Forty Thousand And Xx / 100",
      "Purchase Order": "3125",
      "Before VAT": "240,000.00",
      "Please deliver to us the following at prices, terms and conditions noted below. Substitution, changes or delays are not acceptable unless expressly approved by the undersigned. Goods are subject to our inspection upon delivery. Goods rejected on account of inferior quality, workmanship or hidden defects will be returned. No account will be paid unless your invoice is accompanied by the Purchase Order.": "H",
      "American": "Fence"
    },
    "tables": [
      [
        [
          "Date :",
          "31/08/25"
        ],
        [
          "Goods Receipt PO :",
          "16065"
        ],
        [
          "Credit Term :",
          "90days"
        ],
        [
          "Branch :",
          "Fence Factory"
        ],
        [
          "Page No. :",
          "1"
        ]
      ],
      [
        [
          "#",
          "Item No.",
          "Description",
          "Qty",
          "Price",
          "Discount %",
          "Qty (Stock UoM)",
          "Total"
        ],
        [
          "1",
          "CMGR0001",
          "PVC GRANULES GREEN",
          "50",
          "SAR 4,800.00",
          "0.00",
          "50,000",
          "SAR 240,000.00"
        ],
        [
          "",
          "",
          "",
          "",
          "",
          "",
          "",
          ""
        ],
        [
          "",
          "",
          "",
          "",
          "Total",
          "Excluding Tax",
          "",
          "SAR 240,000.00"
        ]
      ],
      [
        [
          "",
          "p\u00e5)"
        ],
        [
          "23.08.2025",
          "129/25"
        ]
      ],
      [
        [
          "angell sol p\u00e4g",
          "",
          "algiv ub p3)",
          "pg)"
        ],
        [
          "p3, Wi,Lind",
          "",
          "3125",
          "lbll"
        ],
        [
          "2436/25",
          "20.08.2025",
          "",
          ""
        ]
      ],
      [
        [
          "(s)grew Jus)",
          "\u00f6lagli you Juj)",
          "(jb)",
          "\u00f6l-gll",
          "Juplieil",
          "is p"
        ],
        [
          "240,000.00",
          "4,800.00",
          "50.00",
          "ib",
          "\u00e4ills his usgls 39. 40 : sic 40 : sule ib 50.800 :pit\u00e4ll usall ib 50.000 :3hall ujall (di>li) All jub is pubmill ,be Liviall is (sjg\u00fc5lg JL giw)ls :Zuall 23599 :- uo :Ulgiall ,bi-a-gell +974 44503723/ +97444503670 :Ugait 39042200 : gmiall plail is,",
          "1 2"
        ],
        [
          "240,000.00",
          "",
          "50.00",
          "",
          "",
          ""
        ],
        [
          "",
          "",
          "",
          "ricy",
          "sugaw Ju, will ugas,i I jhilo",
          ""
        ],
        [
          "",
          "(BRWAQAQA)",
          "Eight",
          "",
          "(10000-1775-933) whoodl (09) - its clip : clicall put clill",
          "Juples"
        ],
        [
          "",
          "",
          "",
          "",
          "QA48BRWA 0000 0000 0100 00177 5933 : IBAN",
          "p\u00e4g"
        ],
        [
          "",
          "",
          "",
          "",
          "gl labri just oilg 510 Eli sill",
          "sigall"
        ],
        [
          "",
          "",
          "",
          "",
          "",
          ""
        ]
      ],
      [
        [
          "DELIVERY",
          "NOTE"
        ],
        [
          "Number",
          "Date"
        ],
        [
          "4535/25",
          "26.08.2025"
        ]
      ],
      [
        [
          "Delivered Through:",
          "ALHAMAMI, ABDULLAH SALEM A & USMAN"
        ],
        [
          "ID NO:",
          "1113929200 & 2327913758"
        ],
        [
          "MOBILE NO :",
          "55967420 & 33252803"
        ],
        [
          "VEHICLE NO:",
          "4596 & 5015"
        ],
        [
          "NATIONALITY",
          "SAUDI & SAUDI"
        ],
        [
          "",
          "EXP PL 129/25"
        ]
      ],
      [
        [
          "",
          "Number",
          "Date"
        ],
        [
          "Your Order",
          "3125",
          "20.08.2025"
        ]
      ],
      [
        [
          "Item",
          "Description",
          "Code",
          "Unit",
          "Quantity"
        ],
        [
          "1",
          "PVC GRANULES GREEN (RAL 6005) (1250KGS/JUMBO BAG) (NO OF BAGS 40) HS CODE : 39042200 ANY SHORTAGE OR QUALITY COMPLAINT IN ABOVE MATERIALS REPORTED WITHIN 48 HRS (FOURTY EIGHT HRS) OF DELIVERY PLASTO PACK NO COMPLAINT WILL BE DEALT BEYOND THIS QUANTITY OR QUALITY OF MATERIALS SUPPLIED AS ABOVE.",
          "PVC GR 1008 MUST BE IN WRITING TO PERIOD FOR",
          "MT",
          "50"
        ],
        [
          "",
          "One Qty. as above",
          "",
          "",
          ""
        ]
      ],
      [
        [
          "due \u0414\u041b\u0401",
          ""
        ],
        [
          "{cytill",
          "p\u00e4g"
        ],
        [
          "23.08.2025",
          "129/25"
        ]
      ],
      [
        [
          "",
          "algin ub p3)"
        ],
        [
          "20.08.2025",
          "3125"
        ]
      ],
      [
        [
          "3hall ujgll (jb)",
          "se (BAGS)",
          "\u00f6lall",
          "Jupliell",
          "\u0440\u0451,"
        ],
        [
          "50.00",
          "40",
          "jb",
          "dills Jine ugat 39.",
          "1"
        ],
        [
          "",
          "",
          "",
          "40 : see",
          ""
        ],
        [
          "",
          "",
          "",
          "40 : Jule",
          ""
        ],
        [
          "",
          "",
          "",
          "jb 50.800 :pit\u00e4ll vigli",
          ""
        ],
        [
          "",
          "",
          "",
          "ib 50.000 ishall usell",
          ""
        ],
        [
          "",
          "",
          "",
          "(di>lis) All alb is pulmill",
          ""
        ],
        [
          "",
          "",
          "",
          "jbg Liviall is",
          ""
        ],
        [
          "",
          "",
          "",
          "sjg\u00fc5lg DL giv)(",
          ""
        ],
        [
          "",
          "",
          "",
          "23599 :- uo : Ulgirl",
          ""
        ],
        [
          "",
          "",
          "",
          "be - angul",
          ""
        ],
        [
          "",
          "",
          "",
          "+974 44503723/ +97444503670 :Ugail",
          ""
        ],
        [
          "",
          "",
          "",
          "39042200 : guiall plail jos",
          ""
        ],
        [
          "50.00",
          "40",
          "Blood",
          "",
          ""
        ],
        [
          "",
          "",
          "",
          "",
          ""
        ]
      ],
      [
        [
          "(AS)",
          "will",
          "lec ', giall JJC",
          "glull is,",
          "(is juist ) juisll pubill js,"
        ],
        [
          "sincell",
          "pilall",
          "is",
          "",
          "HS Code"
        ],
        [
          "ib 50.000",
          "ib 50.800",
          "Jb I us 40.000",
          "in. Juin this sales",
          "39042200"
        ],
        [
          "",
          "",
          "",
          "",
          ""
        ]
      ],
      [
        [
          "4596AXA",
          "VEHICLE REG N. NO."
        ],
        [
          "40290 Kg",
          "1st Weight"
        ],
        [
          "14790 Kg",
          "2nd Weight"
        ],
        [
          "25500 Kg",
          "NET Weight"
        ]
      ],
      [
        [
          "CODE",
          "COSEC. NO.",
          "DATE",
          "TIME"
        ],
        [
          "",
          "30/05/2025",
          "08.25.A",
          ""
        ],
        [
          "",
          "30/08/2025",
          "",
          ""
        ],
        [
          "",
          "73239",
          "",
          ""
        ]
      ],
      [
        [
          "WEIGHTBRIDGE TICKET PRINT",
          "CODE",
          "COSEC. NO.",
          "DATE",
          "TIME",
          "5015ERA",
          "VEHICLE REG N. NO."
        ],
        [
          "PGGN",
          "",
          "30/08/2025",
          "08:27 AM",
          "",
          "40420 Kg",
          "1st Weight"
        ],
        [
          "",
          "",
          "30/08/2025",
          "11.14.AM",
          "",
          "15000 Kg",
          "2nd Weight"
        ],
        [
          "",
          "",
          "73241",
          "",
          "",
          "25420 Kg",
          "NET Weight"
        ]
      ],
      [
        [
          "Item Code",
          "DESCRIPTION OF GOODS",
          "UoM",
          "QTY",
          "U.PRICE",
          "Line Total"
        ],
        [
          "CMGR0001",
          "PVC GRANULES GREEN",
          "Ton",
          "50.00",
          "4,800.00",
          "240,000.00"
        ],
        [
          "",
          "",
          "Before",
          "VAT",
          "240,000.00",
          ""
        ],
        [
          "",
          "",
          "",
          "VAT",
          "0.00 1",
          ""
        ],
        [
          "",
          "",
          "",
          "TOTAL",
          "240,000.00",
          ""
        ]
      ]
    ]
  },
  "expense_analysis": {
    "vendor_name": "VISION a _J\nthe\n2 30\nastaal\nKINGDOM OF SAUDI ARABIA",
    "invoice_number": "36615",
    "invoice_date": "20/08/2025",
    "total_amount": "Two Hundred Forty Thousand And Xx / 100",
    "currency": "",
    "tax_amount": "0.00",
    "line_items": [
      {
        "description": "PVC GRANULES GREEN",
        "quantity": "50",
        "unit_price": "SAR 240,000.00"
      },
      {
        "description": "PVC GRANULES GREEN",
        "quantity": "50.00",
        "unit_price": "240,000.00"
      }
    ],
    "confidence_scores": {
      "invoice_date": 87.95047760009766,
      "total_amount": 91.53435516357422,
      "invoice_number": 94.61486053466797,
      "vendor_name": 52.361446380615234,
      "tax_amount": 99.50958251953125
    }
  },
  "sap_specific_fields": {
    "po_number": "16065",
    "grn_number": "16065",
    "invoice_number": "No",
    "vendor_name": "",
    "vendor_code": "",
    "amount_sar": "4,800.00",
    "date": "25-01-0362"
  },
  "raw_text": "Goods Receipt PO\nOriginal\nVendor ID\n: S01609\nPLASTO PACK FACTORY W.L.L\nDate\n: 31/08/25\n\"PLOT #8,12th STREET,\nGoods Receipt PO : 16065\nNEW INDUSTRIAL AREA,\nDOHA -\nCredit Term\n: 90days\nQATAR\"\nBranch\n: Fence Factory\nPALANIVELRAJAN U\nPage No.\n: 1\nSupplier Ref. No.\n: INV-129/25\nRef.\n: 16065\nQty\n#\nItem No.\nDescription\nQty\nPrice\nDiscount %\n(Stock\nTotal\nUoM)\n1\nCMGR0001\nPVC GRANULES GREEN\n50\nSAR 4,800.00\n0.00\n50,000\nSAR 240,000.00\nTotal Excluding Tax\nSAR 240,000.00\nRemarks:\nBased on Purchase Request 971. Based on Purchase Orders 3125.\nFor Customer Use\nAbove goods received in good order and condition\nReceive by:\nCustomer's Co. Stamp, Date\nJEDDAH\nTel. :\nTax Reg. No.\n:\nSAUDI ARABIA\nFax :\n300188758500003\nMail :\nRegistered in England No.\n:\nroso; LU\nSOQAR\nLASTO\nPlasto Pack Factory W.L.L.\nUKAS\nINCL9901:2013\nSYSTEMS\nCertificate No. 18804-Q15-001\n0026\nassgrall distinall 5. \" 3 /83LmJ1\naugbas \u00f6jg\u00fclg\n4242, 57\npj\n39\u04231 abjall. 3931 disclipall d\u00e4biall\n23.08.2025\n129/25\ndisgram angell iSlaall. 21422 : its\np\u00e5)\n00966-539201154 : igat\n23.08.2025\n129/25\nangell sol p\u00e4g\nalgiv ub p3)\npg)\np3, Wi,Lind\n20.08.2025\n3125\nlbll\n2436/25\nPAYMENT TERMS: CAD 90 DAYS FEOM THE DATE OF TRUCK CONSIGNMENT NOTE\n\u00f6lagli you\nis\n\u00f6l-gll\nJuplieil\n(s)grew Jus)\nJuj)\n(jb)\np\n\u00e4ills his usgls 39.\n240,000.00\n4,800.00\n50.00\nib\n1\n40 : sic\n40 : sule\n2\nib 50.800 :pit\u00e4ll usall\nib 50.000 :3hall ujall\n(di>li) All jub is pubmill\n,be Liviall is\n(sjg\u00fc5lg JL giw)ls :Zuall\n23599 :- uo :Ulgiall\n,bi-a-gell\n+974 44503723/ +97444503670 :Ugait\n39042200 : gmiall plail is,\n240,000.00\n50.00\nricy sugaw Ju, will ugas,i I jhilo\n(BRWAQAQA) Eight (10000-1775-933) whoodl (09) - its clip : clicall put clill Juples\nQA48BRWA 0000 0000 0100 00177 5933 : IBAN p\u00e4g\ngl labri just oilg 510 Eli sill sigall\nIL\n(sjg\u00fcsla 26 giv Hi\nesel e e 0 P.O.Box LASTO Qatar 23599 KELL\nPlasto Pack Facion\npt\nC.R. No. 60446,\nP.O. Box: 23599, Street No.: 12\nNew Industrial Area, Doha, State of Qatar\nTel: +974)4934181\nAL SRAIYA\nPratestion\nPRICHER\nFax: +974 44503723\nCLIC\nleruss the Last\nE-mail: info@plastopacks.com\nHOURD GROUP\nWebsite : www.plastopacks.com\nro ro \u00e0 UU\nLASTO\nPlasto Pack Factory W.L.L.\nDELIVERY NOTE\nNumber\nDate\n4535/25\n26.08.2025\nM/S BRC INDUSTRIAL SAUDIA CO\nDelivered Through:\nALHAMAMI, ABDULLAH SALEM A & USMAN\nP. O Box : 5489\nID NO:\n1113929200 & 2327913758\nTEL : 6355666\nMOBILE NO :\n55967420 & 33252803\nFAX : 6375474\nVEHICLE NO:\n4596 & 5015\nSAUDI ARABIA\nNATIONALITY\nSAUDI & SAUDI\nNumber\nDate\nEXP PL 129/25\nYour\nOur Refer.\nOrder\n3125\n20.08.2025\nso NO : 2436/25\nCustomer\nProject\nSUPPLY OF PVC COMPOUND\nCode\nDetails\nPlease accept delivery of following, as per your\nCOMPLETE DELIVERY\nItem\nDescription\nCode\nUnit\nQuantity\n1\nPVC GRANULES GREEN\nPVC GR 1008\nMT\n50\n(RAL 6005)\n(1250KGS/JUMBO BAG)\n(NO OF BAGS 40)\nHS CODE : 39042200\nANY SHORTAGE OR QUALITY COMPLAINT IN ABOVE MATERIALS MUST BE\nREPORTED WITHIN 48 HRS (FOURTY EIGHT HRS) OF DELIVERY IN WRITING TO\nPLASTO PACK NO COMPLAINT WILL BE DEALT BEYOND THIS PERIOD FOR\nQUANTITY OR QUALITY OF MATERIALS SUPPLIED AS ABOVE.\nOne Qty. as above\nReceived the material in good condition\nPlasto Pack Factory w.l.l\nyru\nby\nisui\n\u00e4ngeml\ncris\nQueM\nPREPARED BY:\nCHECKED BY:\nCHECKED BY:\nAPPROVED BY:\nFENCE\nARABIA\nCO\n30-08-25\n(STORES)\n(SALES)\n(ACCOUNTS)\n(MANAGER)\nBRC\nWhite (Customer) RECEIVED Yellow\nINDUSTRIAL\n7.227\nC.R. No. 60446.\nP.O. Box: 23599, Street No.: 12\nA1\nBuilding No. 8, Zone No. 81\nNew Industrial Area, Doha, State of Qatar\nTUV\nlibiall\nTel: +974 44934181, Fax: +974 44503723\nwisle\nEEGYEAN\nSUD\nE-mail: info@plastopacks.com\ninfo@plastopacks.com\nISO 9001\nWebsite: www.plastopacks.com\nwww.plastopacks.com cigal\nroro j LU giwl\nISOQAR\nREGISTERED\nLASTO\nPlasto Pack Factory W.L.L.\nUKAS\nMANAGEMENT\nCertificate No. 18804-Q15-001\n0026\ndiagrall dischall 5. \" 3 /83Lmll\ndue \u0414\u041b\u0401\n4242, 57 E-Liv\n{cytill\np\u00e4g\nfall abyall. 39VI declinall debiall\n23.08.2025\n129/25\ndisgrall dogall iSlaall 21422 : its\n00966-539201154 : igats\n129/25 : \u00f6jg\u00fclill pg\naNgell sol p3)\nalgin ub p3)\np3) Will\npg,\n20.08.2025\n3125\n2436/25\nlbll\n3hall ujgll\nse\n\u00f6lall\nJupliell\n\u0440\u0451,\n(jb)\n(BAGS)\ndills Jine ugat 39.\njb\n1\n50.00\n40\n40 : see\n40 : Jule\njb 50.800 :pit\u00e4ll vigli\nib 50.000 ishall usell\n(di>lis) All alb is pulmill\njbg Liviall is\nsjg\u00fc5lg DL giv)(\n23599 :- uo : Ulgirl\nbe - angul\n+974 44503723/ +97444503670 :Ugail\n39042200 : guiall plail jos\n50.00\n40\nBlood\non are 3 gliani liatiml\nsigi519 IL given\n15197518 SIU Firm\nAn\ne Plasto e . of P.O.Box Doha ILLASTO Factory Qatar 23599\nPack\nRh\n5\"\nsik\nC.R. No. 60446,\nP.O. Box: 23599, Street No.: 12\n50\neath\nNew Industrial Area, Doha, State of Qatar\nTel: +974 44934181\nAL SRAIYA\nPaul. donal Experience\nFax: +974 44503723\nCLIC\nTerms the last\nE-mail: info@plastopacks.com\nWebsite : www.plastopacks.com\n2025-01-03626 \"Salguill is,\nthi\n25-08-2025 :-\nQATAR CHAMBER\nState of Qatar\nLiiis\ninjell calill Jgl inglail who Jgyl iiib all citainall\n:ail gic I giiall pul\n:ail gic I sholl pul\nissull jbs slis and 09 jo LS jists J4 givels\ninill jbs dis dual us Ja is jisti sly give\n,Las is Nill dyclinall d\u00e9bialltatis giftely We swall is inall\njhi is will dyclinall d\u00e9bialltatis gittely we swall valuall\n:4il gic il,ill, a j giwall pul\nin greall dyalinall 5 1's\nilliable\n00966539201154\nin greall shall -- st,VI i jall retail\n:0 gilall (u)li, ag,\n129/25\n23-08-2025\n(AS) will\n(is juist )\nlec is ', giall JJC\nglull is,\njuisll pubill js,\nsincell\npilall\nHS Code\nib 50.000\nib 50.800\nJb I us 40.000\nin. Juin this sales\n39042200\nin oycl lgluslei inis gell shall, illogicall J4 (Jai alg) J. ( iclivally shill ii) juliai\nipiall\nOK\n:Simall (ii)\n(whist)\nwww.qatarchamber.com iii, jistyl will jub is is whall wildfall in Lail,\nQatar Chamber of Commerce & Industry\nh\u00f6 a_cl_ing \u00f6jL doj\n2025-15230\nissuall 2,\n60446\n2,\n129/25\n2025-01-03626\n: Geoul p\u00e4ll\n2,1,11 all achieve Livis do is jell just\n:ye , whall viwally\ninill Jas sli, and uses 1 sjisia s. SLL, inc)\ngill\n25/08/2025 :?\nQATAR CHAMBER\n$\nQATAR CHANGEN Origin OF DATAR COMMERCE & Artest CHAMBER a like &\n25/08/2025 :\n2025-15230 in\nWEIGHTBRIDGE\nCODE\nCOSEC. NO.\nDATE\nTIME\n4596AXA\nVEHICLE\nTICKET PRINT\nREG N. NO.\nPGC\n30/05/2025\n08.25.A\n40290 Kg\n1st Weight\n30/08/2025\n14790 Kg\n2nd Weight\n25500 Kg\n73239\nNET Weight\nProduct\n:\nPVC\nGRANULES\nTransporter\nSUPPI jer\nSupplier :\nDia\nPLASTO PACK FACTORY\nCustomer :\n(1) Ref.\nSize\nQty.\n36612\nOrder No.\nInvoice No.\n(2)\n(3)\nDriver's Name:\nOperator\nOAO\nBRC\nIndustrial (Saudia) Limited\nBRC 10/ 1\nP.O. Box : 5489 Jeddah 21422 Tel.: 6355666\n7400777 : Griern of 0EA9 % 0.00\nWEIGHTBRIDGE\nVEHICLE\nCODE\nCOSEC. NO.\nDATE\nTIME\n5015ERA\nREG N. NO.\nTICKET PRINT\nPGGN\n30/08/2025\n08:27 AM\n40420 Kg\n1st Weight\n30/08/2025\n11.14.AM\n15000 Kg\n2nd Weight\n73241\n25420 Kg\nNET Weight\nProduct:\nPVC\nGRANULES\nTransporter:\nSUPPLIER\nSupplier :\nDia\nPLASTO PACK FACTORY\nCustomer :\n(1) Ref.\nSize\nQty.\nOrder No.\nInvoice No. 36615\n(2)\n(3)\nDriver's Name:\nOperator :\nOAO\nBRC\nIndustrial (Saudia) Limited\nBRC 10/ 1\nP.O. Box : 5489 Jeddah 21422 Tel.: 6355666\n7400777 $ Grierr 0819 : 0.00\nVISION I jgj\n2030\nBRC\nACM\nUKAS\nISO 9001:2015\nMANAGEMENT\nREGISTERED\nSYSTEMS\nanjall aslooll\nKINGDOM OF SAUDI ARABIA\nPurchase Order\n3125\n245\nFence Factory\n20/08/2025\nSupplier: S01609\nDelivery Date 31-August-2025\nPLASTO PACK FACTORY W.L.L\nPayment Term:\n90days\nSupplier Address:\nDeliver To:\n\"PLOT #8, 12th STREET,\n658th Street Near Left @ 4th Round About\nNEW INDUSTRIAL AREA,\nDOHA\nJEDDAH\nQATAR\"\nSAUDI ARABIA\nItem Code\nDESCRIPTION OF GOODS\nUoM\nQTY\nU.PRICE\nLine Total\nCMGR0001\nPVC GRANULES GREEN\nTon\n50.00\n4,800.00\n240,000.00\nBefore VAT\n240,000.00\nVAT\n0.00\n1\nTOTAL\n240,000.00\nSAR\nTwo Hundred Forty Thousand And Xx / 100\nOrder Accepted By The Vendor\nPrepared By\nReviewed By\nNoted By\nApproved By\nPlease deliver to us the following at prices, terms and conditions noted below. Substitution, changes or delays are not acceptable unless expressly\napproved by the undersigned. Goods are subject to our inspection upon delivery. Goods rejected on account of inferior quality, workmanship or hidden\ndefects will be returned. No account will be paid unless your invoice is accompanied by the Purchase Order.\nH\nBRC Industrial Saudia Co.\nMixed Closed Joint Stock Company\nIndustrial Area P.O. Box 5489 Jeddah 21422 K.S.A.\nasial\nState\nJus\nTel. Jeddah (012) 6355666 / 6364724 / 6379507 / 6375285\nCapital: S.R. 15,000,000\nTel. Jeddah-3 Fence: (012) 6358 145/ 6358 146 / 6358 147\n(-\nVAT Reg. No: 300188758500003\nTel. Riyadh: (011) 4602692 4602703\n(-11)\nCom. Reg. 4030008649\nTel. Dammam: (013) 8082954\n(.ir)\nChamber of Commerce 1712\nFax Jeddah (012)6375474\n(.11)\nAFA\nAmerican Fence\nFax Dammam: (013) 8124103\nAssociation, Inc.\nE-mail:brcsales@brc.com.sa\nPage 1 of 1\nwebsite:www.brc.com.sa\nPrinted by SAP Business One",
  "confidence_summary": {
    "average_confidence": 85.19,
    "field_count": 5,
    "high_confidence_fields": {
      "total_amount": 91.53435516357422,
      "invoice_number": 94.61486053466797,
      "tax_amount": 99.50958251953125
    },
    "low_confidence_fields": {
      "vendor_name": 52.361446380615234
    }
  }
}

            # ---------- Extraction ----------
            step.step_name = AutomationStep.Step.EXTRACTION
            step.status = AutomationStep.Status.SUCCESS if result_status == "success" else AutomationStep.Status.FAILED
            step.message = message
            step.save()

            if result_status != "success" or not result:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Extraction failed: {message}"}, status=status.HTTP_400_BAD_REQUEST)

            vendor_name = result["sap_specific_fields"].get("vendor_name")
            grn_po_number = result["sap_specific_fields"].get("po_number")
            vendor_code = result["sap_specific_fields"].get("vendor_code")

            print(f"Vendor Name: {vendor_name}, Vendor Code: {vendor_code}, PO Number: {grn_po_number}")

            # If vendor code is not present, try fetching it from SAP
            if not vendor_code:
                vendor_code_resp = get_vendor_code_from_api(vendor_name)
                print(f"Vendor Code Response: {vendor_code_resp}")

                step.step_name = AutomationStep.Step.FETCH_OPEN_GRN  # Even though this is vendor fetching, using GRN step for now

                if vendor_code_resp["status"] != "success":
                    step.status = AutomationStep.Status.FAILED
                    step.message = vendor_code_resp["message"]
                    step.save()

                    automation.status = GRNAutomation.Status.FAILED
                    automation.save(update_fields=["status"])

                    return Response(
                        {
                            "success": False,
                            "message": f"Vendor code fetch failed: {vendor_code_resp['message']}"
                        },
                        status=status.HTTP_400_BAD_REQUEST
                    )

                vendor_code = vendor_code_resp["data"]


            # ---------- Fetch GRNs ----------
            fetch_resp = fetch_grns_for_vendor(vendor_code)
            step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
            step.status = AutomationStep.Status.SUCCESS if fetch_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = fetch_resp["message"]
            step.save()

            if fetch_resp["status"] != "success" or not fetch_resp["data"]:
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"{fetch_resp['message']}"}, status=status.HTTP_400_BAD_REQUEST)

            all_open_grns = fetch_resp["data"]
            print(all_open_grns)

            # ---------- Filter + Matching ----------
            try:
                filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
                print("Filter")
                print(filtered_grns)

                matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)
                print("Matching")
                print(matched_grns)

                step.step_name = AutomationStep.Step.VALIDATION  # preparing for validation
                step.status = AutomationStep.Status.SUCCESS
                step.message = f"Found {len(matched_grns)} matching GRNs."
                step.save()

            except Exception as e:
                step.step_name = AutomationStep.Step.VALIDATION
                step.status = AutomationStep.Status.FAILED
                step.message = f"Matching failed: {str(e)}"
                step.save()

                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Matching failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Validation ----------
            validation_resp = validate_invoice_with_grn(result, matched_grns)

            print("Validaton")
            print(validation_resp)

            step.step_name = AutomationStep.Step.VALIDATION
            step.status = AutomationStep.Status.SUCCESS if validation_resp["status"] == "SUCCESS" else AutomationStep.Status.FAILED
            step.message = validation_resp["reasoning"]
            step.save()

            if validation_resp["status"] != "SUCCESS":
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Validation failed: {validation_resp['reasoning']}"}, status=status.HTTP_400_BAD_REQUEST)

            validated_grns = validation_resp["payload"]

            # ---------- Create Invoice ----------
            invoice_resp = create_invoice(validated_grns)
            print("Invoice")
            print(invoice_resp)

            step.step_name = AutomationStep.Step.BOOKED
            step.status = AutomationStep.Status.SUCCESS if invoice_resp["status"] == "success" else AutomationStep.Status.FAILED
            step.message = invoice_resp["message"]
            step.save()

            if invoice_resp["status"] != "success":
                automation.status = GRNAutomation.Status.FAILED
                automation.save(update_fields=["status"])
                return Response({"success": False, "message": f"Invoice creation failed: {invoice_resp['message']}"}, status=status.HTTP_400_BAD_REQUEST)

            # ---------- Mark Completed ----------
            automation.status = GRNAutomation.Status.COMPLETED
            automation.completed_at = timezone.now()
            automation.save(update_fields=["status", "completed_at"])

            # ---------- Final Response ----------
            return Response({
                "success": True,
                "message": f"Your {self.case_type.replace('_', ' ')} automation has been queued successfully.",
                "automation_status": automation.status,
                "step": {
                    "id": step.id,
                    "step_name": step.step_name,
                    "status": step.status,
                    "updated_at": step.updated_at,
                    "message": step.message
                },
                "validated_data": validated_grns,
                "invoice": invoice_resp["data"]
            }, status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class OneToOneAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_ONE


class OneToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.ONE_TO_MANY


class ManyToManyAutomationUploadView(BaseAutomationUploadView):
    case_type = GRNAutomation.CaseType.MANY_TO_MANY


import os
import logging
import requests
from datetime import date
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser

from sap_integration.sap_service import SAPService

logger = logging.getLogger(__name__)


SERVICE_LAYER_URL = os.getenv("SAP_SERVICE_LAYER_URL", "").rstrip("/")
ATTACHMENT_PATH = os.getenv("SAP_ATTACHMENT_PATH", "C:\\SAP\\Attachments")  # UNC path or local folder


class UploadAttachmentView(APIView):
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request, *args, **kwargs):
        """
        Uploads a PDF file to SAP B1 Attachments2 and returns the AbsoluteEntry.
        """
        uploaded_file = request.FILES.get("file")
        if not uploaded_file:
            return Response({"error": "No file uploaded"}, status=status.HTTP_400_BAD_REQUEST)

        # Ensure SAP session
        SAPService.ensure_session()

        # Build attachment name details
        filename, ext = os.path.splitext(uploaded_file.name)
        ext = ext.lstrip(".").lower()

        # Save the file into the SAP attachments folder
        today = date.today().strftime("%Y%m%d")
        save_dir = os.path.join(ATTACHMENT_PATH, today)
        os.makedirs(save_dir, exist_ok=True)

        file_path = os.path.join(save_dir, uploaded_file.name)
        with open(file_path, "wb") as f:
            for chunk in uploaded_file.chunks():
                f.write(chunk)

        logger.info(f"File saved to: {file_path}")

        # Register in SAP B1 Attachments2
        url = f"{SERVICE_LAYER_URL}/Attachments2"
        headers = {
            "Cookie": f"B1SESSION={SAPService.session_id}",
            "Content-Type": "application/json",
        }

        payload = {
            "Attachments2_Lines": [
                {
                    "SourcePath": save_dir.replace("\\", "\\\\"),  # escape backslashes for JSON
                    "FileName": filename,
                    "FileExtension": ext,
                }
            ]
        }

        try:
            resp = requests.post(url, headers=headers, json=payload, verify=False, timeout=30)
            resp.raise_for_status()
        except Exception as e:
            logger.exception("Failed to create attachment in SAP B1")
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response(
            {
                "status": "success",
                "message": "File uploaded and registered successfully",
                "data": resp.json(),
            },
            status=status.HTTP_201_CREATED,
        )
