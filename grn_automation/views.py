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
from datetime import timezone
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from .models import GRNAutomation
from .serializers import GRNAutomationSerializer
from .pagination import TenResultsSetPagination


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
        data = request.data.dict()
        data["case_type"] = self.case_type

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
            result = {
                "sap_fields": {
                    # "vendor_code": 'S00274',
                    "vendor_code": "S00274",
                    "po_number": 9,
                    "vendor_name": "JOTUN POWDER COATINGS S.A. CO. LTD"
                }
            }

            # # ---------- Extraction ----------
            # step.step_name = AutomationStep.Step.EXTRACTION
            # step.status = AutomationStep.Status.SUCCESS if result_status == "success" else AutomationStep.Status.FAILED
            # step.message = message
            # step.save()

            # if result_status != "success" or not result:
            #     automation.status = GRNAutomation.Status.FAILED
            #     automation.save(update_fields=["status"])
            #     return Response({"success": False, "message": f"Extraction failed: {message}"}, status=status.HTTP_400_BAD_REQUEST)

            # vendor_name = result["sap_fields"].get("vendor_name")
            # grn_po_number = result["sap_fields"].get("po_number")
            # vendor_code = result["sap_fields"].get("vendor_code")  # TODO: replace with vendor lookup
            # # vendor_code = result['sap_fields'].get('vendor_code', None)

            # print(vendor_name, vendor_code)

            # if not vendor_code:
            #     print("runnned")
            #     vendor_code = get_vendor_code_from_api(vendor_name)
            #     print(vendor_code)

            # # ---------- Fetch GRNs ----------
            # fetch_resp = fetch_grns_for_vendor(vendor_code)
            # step.step_name = AutomationStep.Step.FETCH_OPEN_GRN
            # step.status = AutomationStep.Status.SUCCESS if fetch_resp["status"] == "success" else AutomationStep.Status.FAILED
            # step.message = fetch_resp["message"]
            # step.save()

            # if fetch_resp["status"] != "success" or not fetch_resp["data"]:
            #     automation.status = GRNAutomation.Status.FAILED
            #     automation.save(update_fields=["status"])
            #     return Response({"success": False, "message": f"GRN fetch failed: {fetch_resp['message']}"}, status=status.HTTP_400_BAD_REQUEST)

            # all_open_grns = fetch_resp["data"]
            # print(all_open_grns)

            # # ---------- Filter + Matching ----------
            # try:
            #     filtered_grns = [filter_grn_response(grn)["data"] for grn in all_open_grns]
            #     print("Filter")
            #     print(filtered_grns)

            #     matched_grns = matching_grns(vendor_code, grn_po_number, filtered_grns)
            #     print("Matching")
            #     print(matched_grns)

            #     step.step_name = AutomationStep.Step.VALIDATION  # preparing for validation
            #     step.status = AutomationStep.Status.SUCCESS
            #     step.message = f"Found {len(matched_grns)} matching GRNs."
            #     step.save()

            # except Exception as e:
            #     step.step_name = AutomationStep.Step.VALIDATION
            #     step.status = AutomationStep.Status.FAILED
            #     step.message = f"Matching failed: {str(e)}"
            #     step.save()

            #     automation.status = GRNAutomation.Status.FAILED
            #     automation.save(update_fields=["status"])
            #     return Response({"success": False, "message": f"Matching failed: {str(e)}"}, status=status.HTTP_400_BAD_REQUEST)

            matched_grns = {
        "vendor_code": "S00274",
        "matched_payload": {
            "CardCode": "S00274",
            "DocDate": "2025-08-09T00:00:00Z",
            "Total Amount": 55200.0,
            "Tax": 7200.0,
            "DocumentLines": [
                {
                    "BaseType": 20,
                    "BaseEntry": 19318,
                    "BaseLine": 0,
                    "Quantity": 2.4,
                    "UnitPrice": 20000.0,
                    "ItemCode": "CMPW0012",
                    "ItemDescription": "\"REBAR EPOXY COATING POWDER, Corrocoat EP-F 4003, Green, 1034167\"",
                    "LineTotal": 48000.0
                }
            ]
        }
    }
            
            invoice_data= {
  "document_analysis": {
    "key_value_pairs": {
      "Description": "EP-F4003 RAL6029 SMO",
      "Discount %": "0.00",
      "Item No.": "CMPW0012",
      "Qty (Stock UoM)": "2,400",
      "Total": "SAR 48,000.00",
      "Tax Reg. No. :": "300188758500003",
      "Remarks:": "Based on Purchase Request 842. Based On Purchase Orders 2734.",
      "Supplier Ref. No.": "2734-CD8425002964",
      "For Customer Use": "Above goods received in good order and condition",
      "Price": "SAR 20,000.00",
      "Total Excluding Tax": "SAR 48,000.00",
      "#": "1",
      "Qty": "2.4",
      "Goods Receipt PO :": "15342",
      "Date": "09/08/25",
      "Credit Term": "90days",
      "Branch": "Dammam",
      "Ref.": "15342",
      "Vendor ID": "S00274",
      "Page No.": "1",
      "JEDDAH": "SAUDI ARABIA",
      "\"POST BOX NO:": "10830",
      "Currency Code": "SAR",
      "Sales Unit Price": "20.00",
      "VAT %": "15.00",
      "Due date": "2025-11-05",
      "Terms of Payment": "pegoJV>",
      "Our Reference": "ESSA, FAWAZ",
      "Product Code": "1034167PX20",
      "Delivery Date:": "2025-08-07",
      "Customer VAT ID": "300188758500003",
      "Purchase Order Number": "2734 DMM",
      "Delivery Address": "leaver asgemell ancluall. w.,l. a5,ue 7795 rual \u0434\u0451, ,4658 siell 19,11 plase 34333 asgemell angell aslaal",
      "Invoice address / orgitall ilgic": "4242 rual p9, 8498 siell ail",
      "paul Discount %": "0.00",
      "Currency:": "SAR",
      "IBAN:": "SA51-4500-0000-0441-6316-0080",
      "Account No.:": "044-163160-001",
      "anjiall das Vat Value": "7,200.00",
      "Fax:": "+966 3 812 1226",
      "VAT NO.": "300403856500003",
      "Swift Code:": "SABBSARI",
      "Trip No / actue p9):": "14928255",
      "ashoal and an is Slolu whayl / Invoice amount to pay (VAT included)": "55,200.00",
      "avjall Jses / VAT Rate %": "15.00",
      "Account Name:": "Jotun Powder Coatings S.A. Co. Ltd",
      "any wall use shall Amount excluding VAT": "48,000.00",
      "Bank Name:": "Saudi Awwal Bank",
      "Customer address": "?? 22423 asgemell angell aSlaal",
      "Tel:": "+966 3 812 1259,",
      "Email:": "Powder.Saudi@Jotun.com",
      "pail ghe Discount Amount": "0.00",
      "Paid up Capital SR": "28,600,000",
      "ashoal and any is the / Total VAT": "7,200.00",
      "agreed and Price Qty": "2400.00",
      "ovailabl pul Invoice Date": "2025-08-07",
      "anall use ghall / Amount excluding VAT": "48,000.00",
      "ovailabl paj Invoice no": "CD8425002964",
      "Juaell p9, Customer Number": "249417",
      "Customer": "l asgemil ancluall. a5,m",
      "C.R. No.": "2050028331",
      "lbll p9, Order No": "W17771264",
      "sibull Jawl": "2050028331",
      "Suel": ", ys alael",
      "+966": "13 812 1259",
      "asgenel and": "ieves well we as,in : ylwall Awl",
      "SABBSARI": "ciaiguil is,",
      "& JW": "28600000",
      "Order No": "W17771264",
      "DELIVER TO:": "agail 1.5' 4658 ill 7795 2) 0000 34333 should Kingdom of Saudi Arabia",
      "Company": "84",
      "ORDER DATE (D.M.Y.)": "07.08.2025",
      "DELIVERY DATE (D.M.Y.)": "07.08.2025",
      "NO-HU-TOT": "1",
      "DT NO.": "14928255",
      "Total litre:": "0",
      "Customer Number:": "249417",
      "DATE (D.M.Y)": "07.08.2025",
      "HAULIER COMPANY": "General Transport - Dammam",
      "SHIP FROM WHSE": "SADV",
      "Number Of Pallets": "1",
      "Authorised Signature": "3",
      "INVOICE TO:": "1.5' is 8498 5 4242 A9, 0000 22423 in Kingdom of Saudi Arabia",
      "INCOTERM": "CIF",
      "Lastpage": "W17771264",
      "Handling Unit Id": "362850390643861394",
      "Del. Qty In Kg": "2,400.00",
      "RELEASED BY": "l'avoo",
      "Page": "1 of 1",
      "Thank you for your Order taken by:": "ESSA, FAWAZ",
      "No.": "1",
      "Total net weight In kg:": "2,400.00",
      "DELNOTE NO.": "39922291",
      "Total number of pcs:": "120",
      "Lot Batch No.": "3998195-1-*-1:2",
      "CUSTOMER P.0.NO.": "2734 DMM",
      "Total gross weight In kg:": "2,496.00",
      "Del. Pcs.": "120",
      "Dammam": "Warehouse",
      "Fence:": "(012) 6358 145/ 6358 146 / 6358 147",
      "Tel. Dammam:": "(013) 8082954",
      "Com. Reg.": "4030008649",
      "VAT Reg. No:": "300188758500003",
      "Fax Dammam:": "(013) 8124103",
      "Deliver To:": "72nd Street DAMMAM SAUDI ARABIA",
      "Supplier Address:": "\"POST BOX 10830 DAMMAM 31443 EASTERN PROVINCE SAUDI ARABIA\"",
      "SAR": "Two Million Three Hundred Thousand And 09 / 100",
      "Tel. Riyadh:": "(011) 4602692 , 4602703",
      "Fax Jeddah": "(012) 6375474",
      "Tel. Jeddah:": "(012) 6355666 / 6364724 / 6379507 / 6375285",
      "Supplier:": "S00274",
      "AFA": "American Fence Association, Inc.",
      "Purchase Order": "2734",
      "Before VAT": "2 2,000,000.08",
      "BY)": "X",
      "Delivery Date": "31-July-2025",
      "Payment Term:": "90days",
      "VAT": "300,000.01",
      "TOTAL": "2,300,000.09",
      "Chamber of": "1712",
      "Capital: S.R.": "15,000,000",
      "Green,": "1034167\"",
      "Surgaret asiat -": "/ / 1100111 :3.17 Upall 7501127 / are again (.11) / 27.8794 again",
      "Transporter Name": "CUSTOMER",
      "Tel.:": "013 8678941",
      "COSEC. NO.": "JOTUN POWDER",
      ":": "- -IT ANVAGES isab - VISAY PLANT - 11224.00",
      "P.O.Box :": "8246 - Dammam 31482",
      "Invoice No.:": "4092",
      "CODE": "11",
      "DATE": "07/08/2025",
      "TIME": "02:24 PM",
      "Customer :": "39922291",
      "Kg": "3670",
      "Industrial (Saudia) Limited": "BRC"
    },
    "tables": [
      [
        [
          "Date",
          ": 09/08/25"
        ],
        [
          "Goods Receipt PO",
          ": 15342"
        ],
        [
          "Credit Term",
          ": 90days"
        ],
        [
          "Branch",
          ": Dammam"
        ],
        [
          "Page No.",
          ": 1"
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
          "CMPW0012",
          "\"REBAR EPOXY COATING",
          "2.4",
          "SAR 20,000.00",
          "0.00",
          "2,400",
          "SAR 48,000.00"
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
          "SAR 48,000.00"
        ]
      ],
      [
        [
          "ovailabl pul Invoice Date",
          "ovailabl paj Invoice no",
          "Juaell p9, Customer Number",
          "zuli Due date",
          "gill bgui Terms of Payment",
          "lbll p9, Order No",
          "leil wall juli Delivery Date:"
        ],
        [
          "2025-08-07",
          "CD8425002964",
          "249417",
          "2025-11-05",
          "pegoJV>",
          "W17771264",
          "2025-08-07"
        ]
      ],
      [
        [
          "Wjhul Our Reference",
          "Juell jo, Customer Reference",
          "Juael avjs iss Customer VAT ID",
          "shill wills #9, Purchase Order Number",
          "EL.,I lim raiss actia RMA Number",
          "alael jo, Currency Code"
        ],
        [
          "ESSA, FAWAZ",
          "",
          "300188758500003",
          "2734 DMM",
          "",
          "SAR"
        ]
      ],
      [
        [
          "dead Qty",
          "asbell p9, Product Code",
          "well Description",
          "whall Unit",
          "aujio% VAT %",
          "anjiall das Vat Value",
          "agreed and Price Qty",
          "02>911 & few Sales Unit Price",
          "paul Discount %",
          "pail ghe Discount Amount",
          "any wall use shall Amount excluding VAT"
        ],
        [
          "120",
          "1034167PX20",
          "psli 6029 JI, 4003 II-5. si EP-F4003 RAL6029 SMO",
          "pcs",
          "15.00",
          "7,200.00",
          "2400.00",
          "20.00",
          "0.00",
          "0.00",
          "48,000.00"
        ]
      ],
      [
        [
          "anall use ghall / Amount excluding VAT",
          "48,000.00"
        ],
        [
          "ashoal and any is the / Total VAT",
          "7,200.00"
        ],
        [
          "ashoal and an is Slolu whayl / Invoice amount to pay (VAT included)",
          "55,200.00"
        ],
        [
          "avjall Jses / VAT Rate %",
          "15.00"
        ]
      ],
      [
        [
          "Customer Number:",
          "CUSTOMER P.0.NO.",
          "ORDER DATE (D.M.Y.)",
          "IMO No.",
          "Company",
          "Order No",
          "Page"
        ],
        [
          "249417",
          "2734 DMM",
          "07.08.2025",
          "",
          "84",
          "W17771264",
          "1/1"
        ],
        [
          "SHIP FROM WHSE",
          "HAULIER COMPANY",
          "DELIVERY DATE (D.M.Y.)",
          "INCOTERM",
          "",
          "Number Of Pallets",
          "NO-HU-TOT"
        ],
        [
          "SADV",
          "General Transport - Dammam",
          "07.08.2025",
          "CIF",
          "",
          "1",
          "1"
        ]
      ],
      [
        [
          "No.",
          "Product Code",
          "Description",
          "Lot Batch No.",
          "Handling Unit Id",
          "Del. Pcs.",
          "Del. Qty In Litre",
          "Del. Qty In Kg"
        ],
        [
          "1",
          "1034167PX20",
          "EP-F4003 RAL6029 SMO",
          "3998195-1-*-1:2",
          "362850390643861394",
          "120",
          "",
          "2,400.00"
        ]
      ],
      [
        [
          "TOTALS",
          "",
          "",
          "",
          "",
          ""
        ],
        [
          "Total gross weight In kg:",
          "2,496.00",
          "Total net weight In kg:",
          "2,400.00",
          "Total number of pcs: 120",
          "Total litre: 0"
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
          "CMPW0012",
          "\"REBAR EPOXY COATING POWDER, Corrocoat EP-F 4003, Green, 1034167\"",
          "Ton",
          "100.00",
          "20,000.00",
          "2,000,000.00"
        ],
        [
          "CMPW0012",
          "\"REBAR EPOXY COATING POWDER, Corrocoat EP-F 4003, Green, 1034167\"",
          "Ton",
          "8.00",
          "0.01",
          "0.08"
        ],
        [
          "",
          "",
          "Before",
          "VAT",
          "2 2,000,000.08",
          ""
        ],
        [
          "",
          "",
          "",
          "VAT",
          "300,000.01",
          ""
        ],
        [
          "",
          "",
          "",
          "TOTAL",
          "2,300,000.09",
          ""
        ]
      ],
      [
        [
          "CODE",
          "COSEC. NO.",
          "DATE",
          "TIME",
          "4531JH",
          "VEHICLE REG N. NO."
        ],
        [
          "11 JOTUN",
          "POWDER",
          "07/08/2025",
          "02:24 PM",
          "6260 Kg",
          "1st Weight"
        ],
        [
          "",
          "",
          "07/08/2025",
          "02:51 PM",
          "3670 Kg",
          "2nd Weight"
        ],
        [
          "",
          "",
          "",
          "",
          "2590 Kg",
          "NET Weight"
        ]
      ]
    ]
  },
  "expense_analysis": {
    "vendor_name": "VISION\nwhite\n2 30",
    "invoice_number": "4092",
    "invoice_date": "19/06/2025",
    "total_amount": "Two Million Three Hundred Thousand And 09/100",
    "currency": "",
    "tax_amount": "300,000.01",
    "line_items": [
      {
        "description": "\"REBAR EPOXY COATING 2.4",
        "quantity": "2.4",
        "unit_price": "SAR 48,000.00"
      },
      {
        "quantity": "120",
        "description": "psli 6029 JI, 4003 its si\nEP-F4003 RAL6029 SMO",
        "unit_price": "48,000.00"
      },
      {
        "description": "\"REBAR EPOXY COATING POWDER, Corrocoat EP-F\n4003, Green, 1034167\"",
        "quantity": "100.00",
        "unit_price": "2,000,000.00"
      },
      {
        "description": "\"REBAR EPOXY COATING POWDER, Corrocoat EP-F\n4003, Green, 1034167\"",
        "quantity": "8.00",
        "unit_price": "0,08"
      }
    ],
    "confidence_scores": {
      "invoice_date": 98.38308715820312,
      "total_amount": 99.54412078857422,
      "vendor_name": 62.686336517333984,
      "invoice_number": 99.89984893798828,
      "tax_amount": 99.8010025024414
    }
  },
  "sap_specific_fields": {
    "po_number": "15342",
    "grn_number": "15342",
    "invoice_number": "ovailabl",
    "vendor_name": "BRC Industrial Saudia Co.",
    "vendor_code": "Ref",
    "amount_sar": "20,000.00",
    "date": "19/06/2025"
  },
  "raw_text": "Goods Receipt PO\nOriginal\nVendor ID\n: S00274\nJOTUN POWDER COATINGS S.A. CO. LTD\nDate\n: 09/08/25\n\"POST BOX NO: 10830\nGoods Receipt PO : 15342\nDAMMAM - 31443\nEASTERN PROVINCE\nCredit Term\n: 90days\nSAUDI ARABIA\"\nBranch\n: Dammam\nGhassan.Alsamman@jotun.com\nPage No.\n: 1\nSupplier Ref. No.\n: 2734-CD8425002964\nRef.\n: 15342\nQty\n#\nItem No.\nDescription\nQty\nPrice\nDiscount %\n(Stock\nTotal\nUoM)\n1\nCMPW0012\n\"REBAR EPOXY COATING\n2.4\nSAR 20,000.00\n0.00\n2,400\nSAR 48,000.00\nTotal Excluding Tax\nSAR 48,000.00\nRemarks:\nBased on Purchase Request 842. Based On Purchase Orders 2734.\nFor Customer Use\nAbove goods received in good order and condition\nReceive by:\nCustomer's Co. Stamp, Date\nJEDDAH\nTel. :\nTax Reg. No.\n:\nSAUDI ARABIA\nFax :\n300188758500003\nMail :\nRegistered in England No.\n:\n1/2\nJOTUN\nJotun Protects Property\nawjo \u00f6jg\u00fcl\u00f6\nTAX INVOICE\novailabl pul\novailabl paj\nJuaell p9,\nzuli\ngill bgui\nlbll p9,\nleil wall juli\nInvoice Date\nInvoice no\nCustomer Number\nTerms of Payment\nOrder No\nDelivery Date:\nDue date\n2025-08-07\nCD8425002964\n249417\n2025-11-05\npegoJV>\nW17771264\n2025-08-07\nWjhul\nJuell jo,\nJuael avjs iss\nshill wills #9,\nEL.,I lim\nalael jo,\nOur Reference\nCustomer Reference\nCustomer VAT ID\nPurchase\nraiss actia\nCurrency Code\nOrder Number\nRMA Number\nESSA, FAWAZ\n300188758500003\n2734 DMM\nSAR\nTrip No / actue p9): 14928255\nJuell\nInvoice address / orgitall ilgic\nDelivery Address / admill ulgic\nCustomer\nl asgemil ancluall. a5,m\nleaver asgemell ancluall. w.,l. a5,ue\nJuaell ulgic\n4242 rual p9, 8498 siell ail\n7795 rual \u0434\u0451, ,4658 siell 19,11\nCustomer address\n??\nplase\n22423\n34333\nasgemell angell aSlaal\nasgemell angell aslaal\ndead\nasbell p9,\nwell\nwhall\naujio%\nanjiall das\nagreed and\n02>911 & few\npaul\npail ghe\nany wall use shall\nQty\nProduct Code\nSales\nDiscount\nDescription\nUnit\nDiscount\nAmount\nVAT %\nVat Value\nPrice Qty\nUnit Price\n%\nAmount\nexcluding VAT\n120\n1034167PX20\npsli 6029 JI, 4003 II-5. si\npcs\n15.00\n7,200.00\n2400.00\n20.00\n0.00\n0.00\nEP-F4003 RAL6029 SMO\n48,000.00\nanall use ghall / Amount excluding VAT\n48,000.00\nashoal and any is the / Total VAT\n7,200.00\nashoal and an is Slolu whayl / Invoice amount to pay (VAT included)\n55,200.00\navjall Jses / VAT Rate %\n15.00\nJotun Powder Coatings S.A. Co. Ltd\nBankers:\nobtail\nasgruil angell jengs 5596 was is_ui\nVAT NO. 300403856500003\nBank Name: Saudi Awwal Bank\nJ911 sigaral chill call pul\norganall\n3078 2nd Industrial City\nAccount Name: Jotun Powder Coatings S.A. Co. Ltd\nassemble angell jevgs 5594 was as,ii awl\n300403856500003 will asill\nDammam 34326 6419\nAccount No.: 044-163160-001\norganal\n3078 whil distinal\nKingdom of Saudi Arabia\nIBAN: SA50-4500-0000-0441-6316-0001\n044-163160-001 a9,\n6419 34325 plant\nTel: +966 13 812 1259\nCurrency: SAR\nSA50-4500-0000-0441-6316-0001 COWI A9,\nassemil angell alaal\nFax: +966 13 812 1226\nSwift Code: SABBSARI\nsign JL, alael\n+966 13 812 1259 to\nEmail: Powder.Saudi@Jotun.com\nSABBSARI ciaiguil joj\n+966 13 812 1226 I\nPaid up Capital SR 28,600,000\nBank Name: Saudi Awwal Bank\nPowder.Saudi@Jotun.com.xyll\nC.R. No. 2050028331\nAccount Name: Jotun Powder Coatings S.A. Co. Ltd\nJgyl signal chill relati pul\nwas\nAccount No.: 044-163160-080\nasgenel and ieves well we as,in : ylwall Awl\n& JW 28600000 Earall JWI wis\nIBAN: SA51-4500-0000-0441-6316-0080\norgani\n2050028331 sibull Jawl\nCurrency: USD\n044-163160-080 y A9,\nSwift Code: SABBSARI\nSA51-4500-0000-0441-6316-0080 A9,\nSuel , ys alael\nSABBSARI ciaiguil is,\nJotun Powder Coatings S. A. Co. Ltd.\nJOTUN\nDelivery Ticket\nP.O. Box 10830, Dammam 31443, Kingdom of Saudi Arabia\nTel: +966 3 812 1259, Fax: +966 3 812 1226\nEmail: Powder.Saudi@Jotun.com\n84841492825539922291-1-V17771264-M17771264\nDammam Warehouse\nDELIVER TO:\nINVOICE TO:\nDT NO.\n14928255\nagail\n1.5'\n1.5'\nis\nDATE (D.M.Y)\n4658 ill\n8498\n5\n07.08.2025\n7795 2)\n4242 A9,\nDELNOTE NO.\n0000\n0000\n39922291\n34333 should\n22423 in\nKingdom of Saudi Arabia\nKingdom of Saudi Arabia\nCustomer Number:\nCUSTOMER P.0.NO.\nORDER DATE (D.M.Y.)\nIMO No.\nCompany\nOrder No\nPage\n249417\n2734 DMM\n07.08.2025\n84\nW17771264\n1/1\nSHIP FROM WHSE\nHAULIER COMPANY\nDELIVERY DATE (D.M.Y.)\nINCOTERM\nNumber Of Pallets\nNO-HU-TOT\nSADV\nGeneral Transport - Dammam\n07.08.2025\nCIF\n1\n1\nNo.\nProduct Code\nDescription\nLot Batch No.\nHandling Unit Id\nDel. Pcs.\nDel. Qty In Litre\nDel. Qty In Kg\n1\n1034167PX20\nEP-F4003 RAL6029 SMO\n3998195-1-*-1:2\n362850390643861394\n120\n2,400.00\nTOTALS\nTotal gross weight In kg: 2,496.00\nTotal net weight In kg: 2,400.00\nTotal number of pcs: 120\nTotal litre: 0\nThank you for your Order taken by: ESSA, FAWAZ\nAll goods listed above have been examined and\nl'avoo\n3\nreceived in good order.\nRELEASED BY\nVEHICLE NO\nSECURITY CHECK\nAuthorised Signature\nDate\nStamped and Signed\n:-\nLastpage W17771264\nCUSTOMER COPY\n2/8/221\nVISION\n2\n30\nBRC\nACM\nUKAS\nangawli anjoil calool\n180 8001:2015\nMANAGEMENT\nREGISTERED\nSTATEMS\nKINGDOM OF SAUDI ARABIA\nPurchase Order\n2734\n243\nDammam\n19/06/2025\nSupplier: S00274\nDelivery Date 31-July-2025\nJOTUN POWDER COATINGS S.A. CO. LTD\nPayment Term: 90days\nSupplier Address:\nDeliver To:\n\"POST BOX NO: 10830\n72nd Street\nDAMMAM 31443\nEASTERN PROVINCE\nDAMMAM\nSAUDI ARABIA\"\nSAUDI ARABIA\nItem Code\nDESCRIPTION OF GOODS\nUoM\nQTY\nU.PRICE\nLine Total\nCMPW0012\n\"REBAR EPOXY COATING POWDER, Corrocoat EP-F\nTon\n100.00\n20,000.00\n2,000,000.00\n4003, Green, 1034167\"\nCMPW0012\n\"REBAR EPOXY COATING POWDER, Corrocoat EP-F\nTon\n8.00\n0.01\n0.08\n4003, Green, 1034167\"\nBefore VAT\n2 2,000,000.08\nVAT\n300,000.01\nTOTAL\n2,300,000.09\nSAR\nTwo Million Three Hundred Thousand And 09 / 100\nPrepared By\nOrder Accepted By The Vendor\nReviewed X BY)\nNoted By\nApproved By\nPlease deliver to us the following at prices, terms and conditions noted below. Substitution, changes or delays are not acceptable unless expressly approved\nby the undersigned. Goods are subject to our inspection upon delivery. Goods rejected on account of inferior quality, workmanship or hidden defects will be\nreturned. No account will be paid unless your invoice is accompanied by the Purchase Order.\n1\nBRC Industrial Saudia Co.\nasiat\nMixed Closed Joint Stock Company\nSurgaret\n-\nIndustrial Area - P.O. Box 5489 Jeddah 21422 K.S.A.\nJul only\n(+1Y) TOTAL / / REVENUE 1100111 :3.17 Upall\nTel. Jeddah: (012) 6355666 / 6364724 / 6379507 / 6375285\nCapital: S.R. 15,000,000\n(.ir)\nREPREV\n7501127\n/\nare\nagain\nTel. Jeddah-3 Fence: (012) 6358 145/ 6358 146 / 6358 147\n(.11)\n/\nVAT Reg. No: 300188758500003\n-\n-\n27.8794\nagain\nTel. Riyadh: (011) 4602692 , 4602703\nCom. Reg. 4030008649\n-\n(+1r) A-ATROE\nTel. Dammam: (013) 8082954\nChamber of Commerce 1712\nIVIT\nagains\n(.17) 10.00 USE\nFax Jeddah (012) 6375474\n(.)r) plas\nAFA\nAmerican Fence\nFax Dammam: (013) 8124103\nAssociation, Inc.\nwebsite:www.brc.com.sa\nE-mail:brcsales@brc.com.sa\nPage 1 of 1\nPrinted by SAP Business One\nWEIGHTBRIDGE\nVEHICLE\nTICKET PRINT\nCODE\nCOSEC. NO.\nDATE\nTIME\n4531JH\nREG N. NO.\n11\nJOTUN POWDER\n07/08/2025\n02:24 PM\n6260 Kg\n1st Weight\n07/08/2025\n02:51 PM\n3670 Kg\n2nd Weight\n2590 Kg\nNET Weight\n04\nJOTUN POWDER\n2400KG\nSupplier :\nDia\nCustomer :\n39922291\n(1) Ref.\nSize\nQty.\nInvoice No.: 4092\n(2)\nTransporter Name\nCUSTOMER\n(3)\nDriver's Name\nRASHID\nBRC\nIndustrial (Saudia) Limited\nBRC 10/1\nozy 7500777 : - -IT ANVAGES : isab - VISAY PLANT - 11224.00\nP.O.Box : 8246 - Dammam 31482 - Tel.: 013 8678941 Jeddah Tel.: 012 6355666",
  "confidence_summary": {
    "average_confidence": 92.06,
    "field_count": 5,
    "high_confidence_fields": {
      "invoice_date": 98.38308715820312,
      "total_amount": 99.54412078857422,
      "invoice_number": 99.89984893798828,
      "tax_amount": 99.8010025024414
    },
    "low_confidence_fields": {
      "vendor_name": 62.686336517333984
    }
  }
}

            # ---------- Validation ----------
            # validation_resp = validate_invoice_with_grn(result, matched_grns)
            validation_resp = validate_invoice_with_grn(invoice_data, matched_grns)

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
                "message": "Success",
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
