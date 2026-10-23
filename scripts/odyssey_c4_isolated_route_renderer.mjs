// Present a trusted isolated Python Core/E3 C4 receipt through the REAL n8n
// route code and browser validator. No server, network, or vault writes here.
import {readFileSync} from "node:fs";
import {validateProductResponse} from "../odyssey_web/client.js";

const source=readFileSync(new URL("../workflows/odyssey-online.ts",import.meta.url),"utf8");
const marker="const routeCode = `";
const start=source.indexOf(marker);
const end=source.indexOf("`;\n\nconst finishCode =",start+marker.length);
const helpersMarker="const costHelpers = String.raw`";
const helpersStart=source.indexOf(helpersMarker);
const helpersEnd=source.indexOf("`;\n\nconst routeCode",helpersStart+helpersMarker.length);
if (start<0||end<=start||helpersStart<0||helpersEnd<=helpersStart)throw Error("Cannot extract deployed route");
const compiled=source.slice(start+marker.length,end)
 .replace("${pricingSnapshotLiteral}",JSON.stringify({as_of:"2026-10-23",models:{}}))
 .replace("${costHelpers}",source.slice(helpersStart+helpersMarker.length,helpersEnd));
const route=new Function("$input","$",compiled);
const raw=readFileSync(0,"utf8");
if(raw.length>200_000)throw Error("Receipt too large");
const receipt=JSON.parse(raw);
if(typeof receipt.request_id!=="string"||!receipt.request_id.startsWith("c4-isolated-"))
 throw Error("Only isolated synthetic receipts allowed");
const output=route({first:()=>({json:receipt})},name=>{
 if(name!=="Odyssey product request")throw Error("unexpected request context");
 return {item:{json:{body:{request_id:receipt.request_id}}}};
})[0].json;
const actual=validateProductResponse(output);
if(actual.status!=="partial"||actual.kind!=="acknowledgement"||
 !actual.message.includes("ha guardado parte")||
 !actual.message.includes("No he podido verificar la causa exacta")||
 !actual.note_result_snapshot)
 throw Error("C4 partial not grounded: "+JSON.stringify({status:actual.status,kind:actual.kind,message:actual.message,expected_snapshot:receipt.note_result_snapshot,actual_snapshot:actual.note_result_snapshot,raw_snapshot:output.note_result_snapshot}).slice(0,1700));
console.log(JSON.stringify({
 route:output.route,
 status:actual.status,
 kind:actual.kind,
 message:actual.message,
 note_snapshot:actual.note_result_snapshot,
 pass:true,
 original_reason:receipt.product_reason,
 written_ids:receipt.affected_stable_note_ids,
}));
