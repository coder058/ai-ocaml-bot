import test from "node:test";
import assert from "node:assert/strict";
import { cohortAccounting, executionView } from "../lib/execution-view.ts";

// SOURCE: synthetic stocks, fills, dates and fees exercise cohort boundaries;
// no fixture result is market evidence or calibrated strategy performance.
const now=Date.parse("2026-10-04T20:00:00Z");
const order=(id,side,at)=>({id,clientOrderId:"aibotstk"+id,symbol:"QQQ",side,
  status:"filled",filledQty:"1",submittedAt:`2026-10-04T${at}Z`});
const fill=(id,side,qty,price,at)=>({id,orderId:id,symbol:"QQQ",side,qty,price,
  transactionTime:`2026-10-04T${at}Z`});
const fixture=()=>({generatedAt:"2026-10-04T19:59:30Z",ordersComplete:true,fillsComplete:true,journal:[],
  orders:[order("old","buy","19:00:00"),order("carry","sell","19:40:00"),
    order("new","buy","19:45:00"),order("exit","sell","19:46:00")],
  fills:[fill("old","buy","1","100","19:00:01"),fill("carry","sell","1","110","19:40:01"),
    fill("new","buy","1","100","19:45:01"),fill("exit","sell","0.4","110","19:46:01")],
  positions:[{symbol:"QQQ",qty:"0.6",marketValue:"66",unrealizedPl:"6",protected:false}],
  cryptoFees:{pagesComplete:true,attributedToBot:true,activityRows:1,usdFeeRows:1,btcFeeRows:0,
    unclassifiedRows:0,usdNetAmount:"-100",btcFeeQty:"0",btcFeeValueAtActivityPriceUsd:"0",
    fetchedAt:"2026-10-04T19:59:00Z"}});

test("new cohort reports only exact new entry/exit FIFO groups, excluding carry-in and aggregate historical fees",()=>{
  const t=fixture(),r=cohortAccounting(t,now);
  assert.equal(r.available,true);assert.equal(r.matchedExitGroups,1);
  assert.equal(r.carryInExitGroups,1);assert.equal(r.grossRealized,4);
  assert.equal(r.netRealized,null);assert.equal(executionView(t,now).cohortAccounting.grossRealized,4);
  assert.ok(!JSON.stringify(r).includes("19:00"));
});

test("partial exits can form several groups without inventing whole round trips or net results",()=>{
  const t=fixture();t.orders.push(order("exit2","sell","19:47:00"));
  t.fills.push(fill("exit2","sell","0.2","105","19:47:01"));
  t.positions[0].qty="0.4";t.positions[0].marketValue="44";
  const r=cohortAccounting(t,now);
  assert.equal(r.matchedExitGroups,2);assert.equal(r.grossRealized,5);
  assert.equal(r.netRealized,null);
});

test("incomplete, unmatched, conflicting or future broker records withhold all cohort P&L",()=>{
  for(const change of [
    t=>t.fillsComplete=false,
    t=>t.ordersComplete=false,
    t=>t.generatedAt="2026-10-04T20:00:00.001Z",
    t=>t.fills[3].transactionTime="2026-10-04T20:00:00.001Z",
    t=>t.fills[3].transactionTime=null,
    t=>t.fills[3].qty="2",
    t=>t.fills.push({...t.fills[3],price:"999"}),
    t=>t.fills[3].symbol="NVDA",
  ]){
    const t=fixture();change(t);const r=cohortAccounting(t,now);
    assert.equal(r.available,false);assert.equal(r.grossRealized,null);
    assert.equal(r.matchedExitGroups,null);assert.equal(r.netRealized,null);
  }
});

test("a pre-cohort submitted entry is not relabeled new because it filled later",()=>{
  const t=fixture();t.orders[2].submittedAt="2026-10-04T19:00:00Z";
  const r=cohortAccounting(t,now);
  assert.equal(r.matchedExitGroups,0);assert.equal(r.carryInExitGroups,2);
  assert.equal(r.grossRealized,0);assert.equal(r.netRealized,null);
});
